import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .enums import MemberStatus
from .models import ProjectInvitation, ProjectMember, ProjectModel

User = get_user_model()


class ProjectAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123",
            jira_id="JIRA-USER-123",
            jira_api_token="mock-api-token",
        )

        self.invitee = User.objects.create_user(
            email="invitee@test.com",
            password="password123",
            jira_id="JIRA-USER-999",
            jira_api_token="invitee-token",
        )

        self.client.force_authenticate(user=self.user)
        self.list_create_url = reverse("project-list")

        self.project = ProjectModel.objects.create(
            title="Base Project",
            jira_id="J-BASE",
            jira_project_key="BASE",
            site_url="https://site.atlassian.net",
            owner=self.user,
        )

        self.valid_payload = {
            "title": "Automated Test Project",
            "description": "Testing Jira Handshake",
            "jira_project_key": "TEST",
            "site_url": "https://mysite.atlassian.net",
        }

    def get_json_data(self, response):
        return json.loads(response.content)

    @patch("core.services.JiraProjectService.create_jira_project")
    def test_create_project_success(self, mock_jira):
        mock_jira.return_value = "10001"

        response = self.client.post(self.list_create_url, self.valid_payload)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data["success"], True)
        self.assertEqual(data["message"], "Operation successful")
        self.assertEqual(data["data"]["jira_id"], "10001")
        self.assertEqual(data["data"]["can_edit"], True)

    def test_list_projects_pagination(self):
        for i in range(3):
            ProjectModel.objects.create(
                title=f"Project {i}",
                jira_id=f"J-{i}",
                jira_project_key=f"K{i}",
                site_url="https://site.atlassian.net",
                owner=self.user,
            )

        response = self.client.get(self.list_create_url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("meta", data)
        self.assertEqual(data["meta"]["count"], 4)
        self.assertIsInstance(data["data"], list)
        self.assertEqual(len(data["data"]), 4)

    def test_security_access_denied(self):
        ProjectModel.objects.create(
            title="User A Project",
            jira_id="999",
            jira_project_key="UA",
            site_url="https://site.atlassian.net",
            owner=self.user,
        )

        user_b = User.objects.create_user(
            email="userb@test.com",
            password="password",
            jira_id="JIRA-USER-456",
            jira_api_token="mock-token-b",
        )
        self.client.force_authenticate(user=user_b)

        response = self.client.get(self.list_create_url)
        data = self.get_json_data(response)

        self.assertEqual(len(data["data"]), 0)

    def test_validation_error_format(self):
        bad_payload = self.valid_payload.copy()
        bad_payload["jira_project_key"] = "lower"

        response = self.client.post(self.list_create_url, bad_payload)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(data["success"], False)
        self.assertEqual(data["code"], "ERROR_400")
        self.assertIn("errors", data)

    @patch("project.serializers.send_invitation_email.delay")
    def test_invite_user_success(self, mock_email_task):
        """
        Test that the invite endpoint creates an invitation record and triggers Celery.
        """
        url = reverse("project-invite", kwargs={"pk": self.project.id})
        payload = {"email": "invitee@test.com", "is_admin": False}

        response = self.client.post(url, payload)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data["data"]["detail"], "Invitation sent successfully.")
        self.assertTrue(ProjectInvitation.objects.filter(invitee=self.invitee).exists())
        mock_email_task.assert_called_once()

    @patch("core.services.JiraProjectService.add_user_to_jira_project")
    def test_accept_invitation_success(self, mock_jira_sync):
        """
        Test successful invitation acceptance and membership creation.
        """
        invitation = ProjectInvitation.objects.create(
            project=self.project,
            invitee=self.invitee,
            invited_by=self.user,
            is_admin=True,
        )

        self.client.force_authenticate(user=self.invitee)
        url = reverse("accept-invitation", kwargs={"token": invitation.token})

        response = self.client.post(url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(data["data"]["detail"], "Joined project successfully.")
        self.assertTrue(
            ProjectMember.objects.filter(
                user=self.invitee, project=self.project
            ).exists()
        )
        mock_jira_sync.assert_called_once()

    def test_accept_invitation_wrong_user_fails(self):
        """
        Test that a user cannot accept an invitation meant for someone else.
        """
        invitation = ProjectInvitation.objects.create(
            project=self.project, invitee=self.invitee, invited_by=self.user
        )

        hacker = User.objects.create_user(
            email="hacker@test.com", password="p", jira_id="H", jira_api_token="T"
        )
        self.client.force_authenticate(user=hacker)

        url = reverse("accept-invitation", kwargs={"token": invitation.token})
        response = self.client.post(url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(data["errors"]["detail"], "Forbidden or expired invitation.")

    def test_accept_expired_invitation_fails(self):
        """
        Test that expired tokens result in a 400 error.
        """
        invitation = ProjectInvitation.objects.create(
            project=self.project,
            invitee=self.invitee,
            invited_by=self.user,
            expires_at=timezone.now() - timezone.timedelta(days=8),
        )

        self.client.force_authenticate(user=self.invitee)
        url = reverse("accept-invitation", kwargs={"token": invitation.token})

        response = self.client.post(url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(data["success"], False)
        self.assertEqual(data["errors"]["detail"], "Forbidden or expired invitation.")

    def test_non_admin_member_cannot_invite(self):
        """
        Ensure a project member without is_admin=True
        cannot invite others.
        """
        regular_user = User.objects.create_user(
            email="regular@test.com",
            password="p",
            jira_id="J-REG",
            jira_api_token="somethign random",
        )
        ProjectMember.objects.create(
            project=self.project,
            user=regular_user,
            is_admin=False,
            status=MemberStatus.MEMBER,
        )

        self.client.force_authenticate(user=regular_user)

        url = reverse("project-invite", kwargs={"pk": self.project.id})
        payload = {"email": "newbie@test.com", "is_admin": False}
        response = self.client.post(url, payload)
        data = self.get_json_data(response)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(data["success"], False)
        self.assertEqual(
            data["errors"]["detail"], "Only project admins can invite users."
        )
