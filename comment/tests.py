# Create your tests here.
import json
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from comment.models import CommentModel
from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from ticket.models import Ticket

User = get_user_model()


class CommentAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123",
            jira_id="JIRA-USER-123",
        )
        self.user.user_id = uuid4()
        self.user.save()

        self.project = ProjectModel.objects.create(
            title="Comment Project",
            jira_id="PROJ-101",
            jira_project_key="COM",
            site_url="https://site.atlassian.net",
            owner=self.user,
            is_archived=False,
        )

        ProjectMember.objects.create(
            project=self.project,
            user=self.user,
            status=MemberStatus.MEMBER,
            is_admin=True,
        )

        self.ticket = Ticket.objects.create(
            title="Test Ticket",
            project=self.project,
            reporter=self.user,
            jira_id="TICK-101",
        )

        self.client.force_authenticate(user=self.user)
        self.list_url = reverse(
            "ticket-comment-list", kwargs={"ticket_pk": self.ticket.id}
        )

    def get_json_data(self, response):
        return json.loads(response.content)

    @patch("core.services.JiraProjectService.add_comment_to_jira")
    def test_create_comment_standardized_response(self, mock_jira):
        """
        Test that creating a comment returns the standardized JSON envelope.
        """
        mock_jira.return_value = "JIRA-99"
        payload = {"message": "Standardized test"}

        response = self.client.post(self.list_url, payload)
        data = self.get_json_data(response)

        # Assert Envelope Structure
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data["success"], True)
        self.assertEqual(data["message"], "Operation successful")

        # Assert Data content
        self.assertEqual(data["data"]["message"], "Standardized test")
        self.assertEqual(data["data"]["jira_id"], "JIRA-99")

    def test_list_comments_pagination_envelope(self):
        """
        Test that paginated lists move 'results' to 'data' and fill 'meta'.
        """
        CommentModel.objects.create(
            message="Comment 1", ticket=self.ticket, commentator=self.user
        )

        response = self.client.get(self.list_url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(data["success"])

        # In your renderer: 'results' becomes 'data', and meta is extracted
        self.assertIsInstance(data["data"], list)
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["meta"]["count"], 1)
        self.assertIn("next", data["meta"])

    @patch("core.services.JiraProjectService.update_jira_comment")
    def test_update_comment_success(self, mock_jira):
        """
        Verify update logic and standardized response.
        """
        comment = CommentModel.objects.create(
            message="Old message",
            ticket=self.ticket,
            commentator=self.user,
            jira_id="J-UPDATE",
        )
        url = reverse(
            "ticket-comment-detail",
            kwargs={"ticket_pk": self.ticket.id, "pk": comment.id},
        )

        payload = {"message": "New message"}
        response = self.client.put(url, payload)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(data["data"]["message"], "New message")
        mock_jira.assert_called_once()

    def test_delete_comment_204_behavior(self):
        """
        Standardized renderer sets data to None on 204.
        """
        comment = CommentModel.objects.create(
            message="Delete me", ticket=self.ticket, commentator=self.user
        )
        url = reverse(
            "ticket-comment-detail",
            kwargs={"ticket_pk": self.ticket.id, "pk": comment.id},
        )

        # Mock destroy behavior because perform_destroy in your viewset
        # calls JiraProjectService.delete_jira_comment
        with patch("core.services.JiraProjectService.delete_jira_comment") as mock_del:
            mock_del.return_value = True
            response = self.client.delete(url)

        data = self.get_json_data(response)

        # Even though it's 204, the renderer wraps it
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(data["success"], True)
        self.assertIsNone(data["data"])

    def test_error_response_format(self):
        """
        Verify that a 400 error uses the error envelope and custom code.
        """
        # Sending empty message to trigger serializer validation error
        response = self.client.post(self.list_url, {"message": ""})
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(data["success"], False)
        self.assertEqual(data["code"], "ERROR_400")
        self.assertIn("message", data["errors"])  # Serializer error keys
