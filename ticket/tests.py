from unittest.mock import patch

from ddf import G
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from ticket.enums import Category, Priority, Status
from ticket.models import Ticket
from user.models import CustomUser


class TicketServiceTestCase(APITestCase):
    """
    Tests ticket lifecycle and validation.
    """

    def setUp(self):
        self.owner = G(CustomUser)
        self.member = G(CustomUser)
        self.outsider = G(CustomUser)

        self.project = G(
            ProjectModel, owner=self.owner, site_url="https://alpha.atlassian.net"
        )

        G(
            ProjectMember,
            project=self.project,
            user=self.member,
            is_admin=True,
            status=MemberStatus.MEMBER,
        )

        self.list_create_url = reverse(
            "ticket-list", kwargs={"project_id": self.project.id}
        )

    @patch("core.services.jira.JiraProjectService.create_jira_task")
    def test_create_ticket_sync_success(self, mock_jira):
        """
        Verify successful ticket creation and Jira sync.
        """
        mock_jira.return_value = {"key": "JIRA-101"}
        self.client.force_authenticate(user=self.owner)

        payload = {
            "name": "Implement OAuth",
            "description": "Critical security feature",
            "category": Category.DEVELOPMENT,
            "priority": Priority.HIGH,
        }

        response = self.client.post(self.list_create_url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Ticket.objects.first().jira_id, "JIRA-101")

    @patch("core.services.jira.JiraProjectService.update_jira_task")
    def test_non_reporter_cannot_close_ticket(self, mock_jira):
        """
        Verify that users who didn't report the ticket cannot close it.
        """
        ticket = G(Ticket, project=self.project, reporter=self.owner)

        self.client.force_authenticate(user=self.member)
        url = reverse(
            "ticket-detail", kwargs={"project_id": self.project.id, "pk": ticket.id}
        )

        response = self.client.patch(url, {"status": Status.CLOSED})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("You can not close the ticket", str(response.data))

    @patch("core.services.jira.JiraProjectService.update_jira_task")
    def test_reporter_can_close_ticket(self, mock_jira):
        """
        Verify that the reporter of a ticket can successfully close it.
        """
        ticket = G(Ticket, project=self.project, reporter=self.member)

        self.client.force_authenticate(user=self.member)
        url = reverse(
            "ticket-detail", kwargs={"project_id": self.project.id, "pk": ticket.id}
        )

        response = self.client.patch(url, {"status": Status.CLOSED})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.CLOSED)

    def test_prevent_ticket_move_to_different_site(self):
        """
        Verify that tickets cannot be moved to a project on a different Jira site.
        """
        other_site_project = G(ProjectModel, site_url="https://different.atlassian.net")
        ticket = G(Ticket, project=self.project)

        self.client.force_authenticate(user=self.owner)
        url = reverse(
            "ticket-detail", kwargs={"project_id": self.project.id, "pk": ticket.id}
        )

        response = self.client.patch(url, {"project": str(other_site_project.id)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("different Jira site", str(response.data))

    def test_list_all_tickets_shows_relevant_tickets(self):
        """
        Verify that the 'my-tickets' endpoint returns the correct tickets for the user.
        """
        G(Ticket, name="Owned Task", project=self.project, reporter=self.owner)

        self.client.force_authenticate(user=self.owner)

        url = reverse("my-tickets")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(results[0]["name"], "Owned Task")

    def test_outsider_cannot_access_ticket(self):
        """
        Verify that a user who is not a member of the project cannot view the ticket.
        """
        ticket = G(Ticket, project=self.project, reporter=self.owner)

        self.client.force_authenticate(user=self.outsider)

        url = reverse(
            "ticket-detail", kwargs={"project_id": self.project.id, "pk": ticket.id}
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
