from unittest.mock import patch

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
            email="anmol@example.com",
            jira_id="jira-user-123",
            jira_api_token="dummy-token",
            password="password123",
            first_name="Anmol",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            jira_id="jira-user-456",
            jira_api_token="dummy-token",
            password="password123",
            first_name="Other",
        )

        self.project = ProjectModel.objects.create(
            title="Test Project",
            owner=self.user,
            site_url="https://example.atlassian.net",
            is_archived=False,
        )

        ProjectMember.objects.create(
            project=self.project, user=self.user, status=MemberStatus.MEMBER
        )

        self.ticket = Ticket.objects.create(
            name="Fix Bug", jira_id="PROJ-1", project=self.project, reporter=self.user
        )

        self.client.force_authenticate(user=self.user)

        self.list_url = reverse(
            "ticket-comment-list", kwargs={"ticket_pk": self.ticket.id}
        )

    @patch("core.services.JiraProjectService.add_comment_to_jira")
    def test_create_comment_success(self, mock_jira_add):
        """Test creating a comment locally and syncing with Jira."""
        mock_jira_add.return_value = "jira-comment-789"

        data = {"message": "This is a test comment."}
        response = self.client.post(self.list_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CommentModel.objects.count(), 1)

        comment = CommentModel.objects.first()
        self.assertEqual(comment.message, "This is a test comment.")
        self.assertEqual(comment.jira_id, "jira-comment-789")
        self.assertEqual(comment.commentator, self.user)
        mock_jira_add.assert_called_once()

    @patch("core.services.JiraProjectService.add_comment_to_jira")
    def test_create_comment_jira_failure(self, mock_jira_add):
        """If Jira sync fails, the local comment should NOT be created."""
        mock_jira_add.side_effect = Exception("Jira API Error")

        data = {"message": "This should fail."}
        response = self.client.post(self.list_url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CommentModel.objects.count(), 0)

    def test_create_comment_archived_project(self):
        """Cannot comment on a ticket whose project is archived."""
        self.project.is_archived = True
        self.project.save()

        data = {"message": "Archived test"}
        response = self.client.post(self.list_url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("core.services.JiraProjectService.update_jira_comment")
    def test_update_comment_owner(self, mock_jira_update):
        """Owner can update their comment."""
        comment = CommentModel.objects.create(
            message="Old message",
            commentator=self.user,
            ticket=self.ticket,
            jira_id="j1",
        )
        url = reverse(
            "ticket-comment-detail",
            kwargs={"ticket_pk": self.ticket.id, "pk": comment.id},
        )

        data = {"message": "Updated message"}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.message, "Updated message")
        mock_jira_update.assert_called_once()

    def test_update_comment_non_owner(self):
        """Non-owner cannot update someone else's comment."""
        comment = CommentModel.objects.create(
            message="Owner message", commentator=self.other_user, ticket=self.ticket
        )
        url = reverse(
            "ticket-comment-detail",
            kwargs={"ticket_pk": self.ticket.id, "pk": comment.id},
        )

        response = self.client.patch(url, {"message": "Hacked!"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("core.services.JiraProjectService.delete_jira_comment")
    def test_delete_comment_success(self, mock_jira_delete):
        """Deleting locally also triggers Jira deletion."""
        mock_jira_delete.return_value = True
        comment = CommentModel.objects.create(
            message="Bye", commentator=self.user, ticket=self.ticket, jira_id="j-del"
        )
        url = reverse(
            "ticket-comment-detail",
            kwargs={"ticket_pk": self.ticket.id, "pk": comment.id},
        )

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(CommentModel.objects.count(), 0)

    def test_list_comments_visibility(self):
        """User can only see comments for tickets they have access to."""
        CommentModel.objects.create(
            message="Visible", commentator=self.user, ticket=self.ticket
        )

        other_proj = ProjectModel.objects.create(
            title="Private",
            owner=self.other_user,
            site_url="https://other.atlassian.net",
        )

        other_ticket = Ticket.objects.create(
            name="Secret", project=other_proj, jira_id="PRIV-1"
        )

        CommentModel.objects.create(
            message="Hidden", commentator=self.other_user, ticket=other_ticket
        )

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["message"], "Visible")
