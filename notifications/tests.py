from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

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
        self.user = User.objects.create_user(
            email="anmol@test.com", jira_id="j-1", jira_api_token="t", password="p"
        )
        self.project = ProjectModel.objects.create(
            title="Test Proj", owner=self.user, site_url="https://test.atlassian.net"
        )
        ProjectMember.objects.create(
            project=self.project, user=self.user, status=MemberStatus.MEMBER
        )

        self.ticket = Ticket.objects.create(
            name="Test Ticket",
            jira_id="TCK-101",
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
            callbacks = transaction.get_connection().run_on_commit
            transaction.get_connection().run_on_commit = []

            if execute:
                for callback_item in callbacks:
                    if isinstance(callback_item, tuple):
                        callback = callback_item[1]
                    else:
                        callback = callback_item
                    callback()

    @patch("core.services.JiraProjectService.update_jira_task")
    @patch("celery.app.control.Control.revoke")
    @patch("notifications.tasks.run_deadline_notification.apply_async")
    def test_deadline_update_revokes_and_schedules(
        self, mock_apply, mock_revoke, mock_jira
    ):
        """Test that updating a deadline manages Celery tasks correctly."""
        mock_task = MagicMock()
        mock_task.id = "new-task-uuid"
        mock_apply.return_value = mock_task

        new_deadline = timezone.now() + timedelta(days=10)
        data = {"deadline": new_deadline.isoformat()}

        response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_revoke.assert_called_with("old-task-uuid", terminate=True)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.deadline_task_id, "new-task-uuid")
        mock_apply.assert_called_once()

    @patch("core.services.JiraProjectService.update_jira_task")
    @patch("notifications.tasks.run_status_notification.delay")
    def test_status_change_metadata_and_task(self, mock_status_task, mock_jira):
        """Verify status metadata updates and Celery task triggering."""
        data = {"status": Status.IN_PROGRESS}

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.ticket.refresh_from_db()

        self.assertEqual(self.ticket.status, Status.IN_PROGRESS)
        self.assertEqual(self.ticket.status_updated_from, Status.TODO)
        self.assertIsNotNone(self.ticket.status_updated_at)
        mock_status_task.assert_called_with(self.ticket.id)

    @patch("core.services.JiraProjectService.update_jira_task")
    def test_assignee_change_auto_subscribes(self, mock_jira):
        """Ensure new assignee is automatically added to ticket notifications."""
        new_assignee = User.objects.create_user(
            email="new@test.com", jira_id="j-2", jira_api_token="t", password="p"
        )
        ProjectMember.objects.create(
            project=self.project, user=new_assignee, status=MemberStatus.MEMBER
        )

        data = {"assignee": new_assignee.user_id}
        response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        is_subscribed = Notifications.objects.filter(
            ticket=self.ticket, subscriber=new_assignee
        ).exists()
        self.assertTrue(is_subscribed)

    @patch("core.services.JiraProjectService.update_jira_task")
    @patch("celery.app.control.Control.revoke")
    @patch("notifications.tasks.run_deadline_notification.apply_async")
    def test_imminent_deadline_clears_task_id(self, mock_apply, mock_revoke, mock_jira):
        """If deadline is too close, task ID should be cleared and no task scheduled."""
        imminent_deadline = timezone.now() + timedelta(hours=1)
        data = {"deadline": imminent_deadline.isoformat()}

        response = self.client.patch(self.url, data)

        self.ticket.refresh_from_db()
        self.assertIn(self.ticket.deadline_task_id, [None, ""])
        mock_apply.assert_not_called()
