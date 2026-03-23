import json
from datetime import timedelta
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
            expires_at=timezone.now() - timedelta(days=8),
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

    @patch("core.services.JiraProjectService.add_user_to_jira_project")
    def test_accept_invitation_idempotency(self, mock_jira_sync):
        """
        Verify that accepting the same invitation twice handles gracefully.
        """
        invitation = ProjectInvitation.objects.create(
            project=self.project,
            invitee=self.invitee,
            invited_by=self.user,
            is_admin=True,
        )

        self.client.force_authenticate(user=self.invitee)
        url = reverse("accept-invitation", kwargs={"token": invitation.token})

        response1 = self.client.post(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

        response2 = self.client.post(url)
        data2 = self.get_json_data(response2)

        self.assertEqual(response2.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(data2["errors"]["detail"], "Forbidden or expired invitation.")

        self.assertEqual(mock_jira_sync.call_count, 1)


class ProjectMemberAPITests(APITestCase):
    """
    Tests for Project Membership management (Listing, Role Updates, Removal).
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@test.com",
            password="password",
            jira_id="J-OWNER",
            jira_api_token="mock-owner-token",
        )
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="password",
            jira_id="J-ADMIN",
            jira_api_token="mock-admin-token",
        )
        self.member = User.objects.create_user(
            email="member@test.com",
            password="password",
            jira_id="J-MEMBER",
            jira_api_token="mock-member-token",
        )

        self.project = ProjectModel.objects.create(
            title="Membership Project",
            jira_id="PROJ-202",
            jira_project_key="MEM",
            site_url="https://site.atlassian.net",
            owner=self.owner,
        )

        ProjectMember.objects.create(
            project=self.project, user=self.owner, is_admin=True
        )
        self.admin_membership = ProjectMember.objects.create(
            project=self.project, user=self.admin, is_admin=True
        )
        self.member_membership = ProjectMember.objects.create(
            project=self.project, user=self.member, is_admin=False
        )

        self.list_url = reverse(
            "project-member-list", kwargs={"project_id": self.project.id}
        )

        self.get_role_url = lambda uid: reverse(
            "project-member-role",
            kwargs={"project_id": self.project.id, "user_id": uid},
        )

    def test_list_members_ordering(self):
        """
        Verify the members list has first the current user.
        """
        self.client.force_authenticate(user=self.member)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            str(response.data["results"][0]["user_id"]), str(self.member.user_id)
        )

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_promote_member_to_admin_by_owner(self, mockjira):
        """
        Test that an owner can promote a regular member to admin.
        """
        self.client.force_authenticate(user=self.owner)
        url = self.get_role_url(self.member.user_id)

        response = self.client.post(url, {"role": "admin"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.member_membership.refresh_from_db()
        self.assertTrue(self.member_membership.is_admin)

    def test_member_cannot_promote_others(self):
        """
        Test to ensure a regular member can not change anyone's role.
        """
        self.client.force_authenticate(user=self.member)
        url = self.get_role_url(self.admin.user_id)

        response = self.client.post(url, {"role": "member"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_transfer_ownership_flow(self, mock_jira):
        """
        Test that transferring ownership makes the target user the project owner
        and keeps the previous owner as an admin.
        """
        self.client.force_authenticate(user=self.owner)
        url = self.get_role_url(self.admin.user_id)

        response = self.client.post(url, {"role": "owner"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.project.refresh_from_db()
        self.assertEqual(self.project.owner, self.admin)

        prev_owner_mem = ProjectMember.objects.get(
            user=self.owner, project=self.project
        )
        self.assertTrue(prev_owner_mem.is_admin)

    def test_owner_cannot_leave_without_transfer(self):
        """
        Test to ensure that the owner must not be allowed to DELETE themselves from a project
        unless they transfer ownership first.
        """
        self.client.force_authenticate(user=self.owner)
        url = reverse(
            "project-member-remove",
            kwargs={"project_id": self.project.id, "user_id": self.owner.user_id},
        )

        response = self.client.post(url)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Owner cannot leave without transferring ownership.",
        )

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_kick_member_success(self, mock_jira):
        """
        Test that an admin can remove a regular member.
        """
        self.client.force_authenticate(user=self.admin)
        url = reverse(
            "project-member-remove",
            kwargs={"project_id": self.project.id, "user_id": self.member.user_id},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ProjectMember.objects.filter(
                user=self.member, status=MemberStatus.MEMBER
            ).exists()
        )

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_admin_can_promote_member_to_admin(self, mock_jira):
        """
        Admins should be able to promote regular members.
        """
        self.client.force_authenticate(user=self.admin)
        url = self.get_role_url(self.member.user_id)

        response = self.client.post(url, {"project_role": "admin"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_membership.refresh_from_db()
        self.assertTrue(self.member_membership.is_admin)

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_owner_can_demote_admin_to_member(self, mock_jira):
        """
        Only the owner should have the power to demote an admin.
        """
        self.client.force_authenticate(user=self.owner)
        url = self.get_role_url(self.admin.user_id)

        response = self.client.post(url, {"project_role": "member"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin_membership.refresh_from_db()
        self.assertFalse(self.admin_membership.is_admin)

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_admin_cannot_demote_other_admins(self, mock_jira):
        """
        An admin should NOT be able to demote another admin.
        """
        admin2 = User.objects.create_user(
            email="admin2@test.com", password="p", jira_id="J2", jira_api_token="T2"
        )
        ProjectMember.objects.create(project=self.project, user=admin2, is_admin=True)

        self.client.force_authenticate(user=self.admin)
        url = self.get_role_url(admin2.user_id)

        response = self.client.post(url, {"project_role": "member"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_can_leave_project_voluntarily(self):
        """
        A regular member should be able to delete their own membership.
        """
        self.client.force_authenticate(user=self.member)
        url = reverse(
            "project-member-remove",
            kwargs={"project_id": self.project.id, "user_id": self.member.user_id},
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ProjectMember.objects.filter(
                user=self.member, project=self.project, status=MemberStatus.MEMBER
            ).exists()
        )
