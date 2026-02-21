from unittest.mock import patch

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
        self.owner = CustomUser.objects.create_user(
            email="owner@example.com",
            jira_id="jira-owner-123",
            jira_api_token="token123",
            first_name="Project",
            last_name="Owner",
            password="password123",
        )
        self.member = CustomUser.objects.create_user(
            email="member@example.com",
            jira_id="jira-member-456",
            jira_api_token="token456",
            first_name="Regular",
            last_name="Member",
            password="password123",
        )
        self.outsider = CustomUser.objects.create_user(
            email="out@example.com",
            jira_id="jira-out-789",
            jira_api_token="token789",
            first_name="Out",
            password="password123",
        )

        self.project = ProjectModel.objects.create_with_user(
            user=self.owner,
            title="Software Alpha",
            jira_project_key="SA",
            site_url="https://alpha.atlassian.net",
            jira_id="10001",
        )

        ProjectMember.objects.create(
            project=self.project,
            user=self.member,
            is_admin=True,
            status=MemberStatus.MEMBER,
            updated_by=self.owner,
        )

        self.list_create_url = reverse(
            "ticket-list", kwargs={"project_pk": self.project.id}
        )

    @patch("core.services.JiraProjectService.create_jira_task")
    def test_create_ticket_sync_success(self, mock_jira):
        mock_jira.return_value = {"id": "JIRA-101"}
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

    @patch("core.services.JiraProjectService.create_jira_task")
    def test_jira_failure_rolls_back_database(self, mock_jira):
        mock_jira.side_effect = Exception("Jira API Timeout")
        self.client.force_authenticate(user=self.owner)

        payload = {"name": "Ghost Ticket", "category": Category.QA}
        response = self.client.post(self.list_create_url, payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Ticket.objects.count(), 0)

    @patch("core.services.JiraProjectService.update_jira_task")
    def test_non_reporter_cannot_close_ticket(self, mock_jira):
        ticket = Ticket.objects.create(
            name="Secure Task",
            project=self.project,
            jira_id="JIRA-202",
            reporter=self.owner,
            category=Category.RESEARCH,
        )

        self.client.force_authenticate(user=self.member)
        url = reverse(
            "ticket-detail", kwargs={"project_pk": self.project.id, "pk": ticket.id}
        )

        response = self.client.patch(url, {"status": Status.CLOSED})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("You can not close the ticket", str(response.data))

    @patch("core.services.JiraProjectService.update_jira_task")
    def test_reporter_can_close_ticket(self, mock_jira):
        ticket = Ticket.objects.create(
            name="My Task",
            project=self.project,
            jira_id="JIRA-303",
            reporter=self.member,
            category=Category.DEVELOPMENT,
        )

        self.client.force_authenticate(user=self.member)
        url = reverse(
            "ticket-detail", kwargs={"project_pk": self.project.id, "pk": ticket.id}
        )

        response = self.client.patch(url, {"status": Status.CLOSED})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.CLOSED)

    def test_outsider_cannot_access_tickets(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_prevent_ticket_move_to_different_site(self):
        other_site_project = ProjectModel.objects.create_with_user(
            user=self.owner,
            title="Other Site",
            jira_project_key="OS",
            site_url="https://different.atlassian.net",
            jira_id="20002",
        )
        ticket = Ticket.objects.create(
            name="Immobile Task",
            project=self.project,
            jira_id="JIRA-404",
            category=Category.QA,
        )

        self.client.force_authenticate(user=self.owner)
        url = reverse(
            "ticket-detail", kwargs={"project_pk": self.project.id, "pk": ticket.id}
        )

        response = self.client.patch(url, {"project": str(other_site_project.id)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("different Jira site", str(response.data))

    def test_list_all_tickets_shows_relevant_tickets(self):
        Ticket.objects.create(
            name="Owned Task",
            project=self.project,
            jira_id="J1",
            reporter=self.owner,
            category="QA",
        )
        self.client.force_authenticate(user=self.owner)

        url = reverse("my-tickets")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Owned Task")
