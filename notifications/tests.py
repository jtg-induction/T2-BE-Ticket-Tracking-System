from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

from ddf import G
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from notifications.models import Notifications
from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from ticket.models import Status, Ticket

User = get_user_model()


class TicketUpdateNotificationTests(APITestCase):
    def setUp(self):
        self.user = G(User, email="anmol@test.com")

        self.project = G(ProjectModel, owner=self.user)

        G(
            ProjectMember,
            project=self.project,
            user=self.user,
            status=MemberStatus.MEMBER,
        )

        self.ticket = G(
            Ticket,
            project=self.project,
            reporter=self.user,
            status=Status.TODO,
            deadline=timezone.now() + timedelta(days=5),
            deadline_task_id="old-task-uuid",
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse(
            "ticket-detail",
            kwargs={"project_pk": self.project.id, "pk": self.ticket.id},
        )

    @contextmanager
    def captureOnCommitCallbacks(self, execute=True):
        """Helper to capture and optionally execute on_commit callbacks."""
        with transaction.atomic():
            yield
            connection = transaction.get_connection()
            callbacks = connection.run_on_commit
            connection.run_on_commit = []

            if execute:
                for callback_item in callbacks:
                    callback = (
                        callback_item[1]
                        if isinstance(callback_item, tuple)
                        else callback_item
                    )
                    callback()

    @patch("core.services.jira.JiraProjectService.update_jira_task")
    @patch("celery.app.control.Control.revoke")
    @patch("notifications.tasks.run_deadline_notification.apply_async")
    def test_deadline_update_revokes_and_schedules(
        self, mock_apply, mock_revoke, mock_jira
    ):
        mock_task = MagicMock(id="new-task-uuid")
        mock_apply.return_value = mock_task

        new_deadline = timezone.now() + timedelta(days=10)
        response = self.client.patch(self.url, {"deadline": new_deadline.isoformat()})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_revoke.assert_called_with("old-task-uuid", terminate=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.deadline_task_id, "new-task-uuid")

    @patch("core.services.jira.JiraProjectService.update_jira_task")
    @patch("notifications.tasks.run_status_notification.delay")
    def test_status_change_metadata_and_task(self, mock_status_task, mock_jira):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(self.url, {"status": Status.IN_PROGRESS})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.IN_PROGRESS)
        mock_status_task.assert_called_with(self.ticket.id)

    @patch("core.services.jira.JiraProjectService.update_jira_task")
    def test_assignee_change_auto_subscribes(self, mock_jira):
        new_assignee = G(User)
        G(
            ProjectMember,
            project=self.project,
            user=new_assignee,
            status=MemberStatus.MEMBER,
        )

        response = self.client.patch(self.url, {"assignee": new_assignee.user_id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Notifications.objects.filter(
                ticket=self.ticket, subscriber=new_assignee
            ).exists()
        )

    @patch("core.services.jira.JiraProjectService.update_jira_task")
    @patch("celery.app.control.Control.revoke")
    @patch("notifications.tasks.run_deadline_notification.apply_async")
    def test_imminent_deadline_clears_task_id(self, mock_apply, mock_revoke, mock_jira):
        imminent_deadline = timezone.now() + timedelta(hours=1)
        self.client.patch(self.url, {"deadline": imminent_deadline.isoformat()})

        self.ticket.refresh_from_db()
        self.assertIn(self.ticket.deadline_task_id, [None, ""])
        mock_apply.assert_not_called()
