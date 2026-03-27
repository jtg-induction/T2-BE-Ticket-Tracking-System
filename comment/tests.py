from unittest.mock import patch

from ddf import G
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
        self.user = G(User, email="anmol@example.com", first_name="Anmol")
        self.other_user = G(User, email="other@example.com")

        self.project = G(ProjectModel, owner=self.user, is_archived=False)

        G(
            ProjectMember,
            project=self.project,
            user=self.user,
            status=MemberStatus.MEMBER,
        )

        self.ticket = G(Ticket, project=self.project, reporter=self.user)

        self.client.force_authenticate(user=self.user)
        self.list_url = reverse(
            "ticket-comment-list", kwargs={"ticket_pk": self.ticket.id}
        )

    @patch("core.services.jira.JiraProjectService.add_comment_to_jira")
    def test_create_comment_success(self, mock_jira_add):
        """Test creating a comment locally and syncing with Jira."""
        mock_jira_add.return_value = "jira-comment-789"

        data = {"message": "This is a test comment."}
        response = self.client.post(self.list_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CommentModel.objects.count(), 1)

        comment = CommentModel.objects.first()
        self.assertEqual(comment.message, "This is a test comment.")
        self.assertEqual(comment.commentator, self.user)

    @patch("core.services.jira.JiraProjectService.update_jira_comment")
    def test_update_comment_owner(self, mock_jira_update):
        """Owner can update their comment."""
        comment = G(
            CommentModel,
            commentator=self.user,
            ticket=self.ticket,
            message="Old message",
        )

        url = reverse(
            "ticket-comment-detail",
            kwargs={"ticket_pk": self.ticket.id, "pk": comment.id},
        )
        response = self.client.patch(url, {"message": "Updated message"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.message, "Updated message")

    def test_update_comment_non_owner(self):
        """Non-owner cannot update someone else's comment."""
        comment = G(CommentModel, commentator=self.other_user, ticket=self.ticket)

        url = reverse(
            "ticket-comment-detail",
            kwargs={"ticket_pk": self.ticket.id, "pk": comment.id},
        )
        response = self.client.patch(url, {"message": "Hacked!"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_comments_visibility(self):
        """User can only see comments for tickets they have access to."""
        G(CommentModel, commentator=self.user, ticket=self.ticket, message="Visible")

        other_ticket = G(Ticket, project__owner=self.other_user)
        G(
            CommentModel,
            commentator=self.other_user,
            ticket=other_ticket,
            message="Hidden",
        )

        response = self.client.get(self.list_url)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["message"], "Visible")
