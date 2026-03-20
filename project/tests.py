import json
from datetime import timedelta
from unittest.mock import patch

from ddf import G
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from project.enums import MemberStatus
from project.models import ProjectInvitation, ProjectMember, ProjectModel

User = get_user_model()


class ProjectAPITests(APITestCase):
    def setUp(self):
        self.user = G(User, email="test@example.com", jira_id="JIRA-USER-123")
        self.user.set_password("password123")
        self.user.save()

        self.invitee = G(User, email="invitee@test.com", jira_id="JIRA-USER-999")
        self.invitee.set_password("password123")
        self.invitee.save()

        self.client.force_authenticate(user=self.user)
        self.list_create_url = reverse("project-list")

        self.project = G(
            ProjectModel,
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
            ProjectModel.objects.create_with_user(
                user=self.user,
                title=f"Project {i}",
                jira_id=f"J-{i}",
                jira_project_key=f"K{i}",
                site_url="https://site.atlassian.net",
            )

        response = self.client.get(self.list_create_url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(data["meta"]["count"], 3)
        self.assertEqual(len(data["data"]), 3)

    def test_security_access_denied(self):
        G(ProjectModel, owner=self.user)

        user_b = G(User, email="userb@test.com")
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

    @patch("project.services.send_invitation_email.delay")
    def test_invite_user_success(self, mock_email_task):
        url = reverse("project-invite", kwargs={"pk": self.project.id})
        payload = {"user_id": self.invitee.user_id, "is_admin": False}

        response = self.client.post(url, payload)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(data["message"], "Operation successful")
        self.assertTrue(ProjectInvitation.objects.filter(invitee=self.invitee).exists())

    @patch("core.services.JiraProjectService.add_user_to_jira_project")
    def test_accept_invitation_success(self, mock_jira_sync):
        invitation = G(
            ProjectInvitation,
            project=self.project,
            invitee=self.invitee,
            invited_by=self.user,
            is_admin=True,
            is_accepted=False,
            expires_at=timezone.now() + timedelta(days=7),
        )

        self.client.force_authenticate(user=self.invitee)
        url = reverse("accept-invitation", kwargs={"token": invitation.token})

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_accept_invitation_wrong_user_fails(self):
        invitation = G(ProjectInvitation, project=self.project, invitee=self.invitee)

        hacker = G(User)
        self.client.force_authenticate(user=hacker)

        url = reverse("accept-invitation", kwargs={"token": invitation.token})
        response = self.client.post(url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(data["errors"]["detail"], "This invitation is not for you.")

    def test_accept_expired_invitation_fails(self):
        invitation = G(
            ProjectInvitation,
            project=self.project,
            invitee=self.invitee,
            expires_at=timezone.now() - timedelta(days=8),
        )

        self.client.force_authenticate(user=self.invitee)
        url = reverse("accept-invitation", kwargs={"token": invitation.token})

        response = self.client.post(url)
        data = self.get_json_data(response)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(data["success"], False)
        self.assertEqual(data["message"], "Expired or invalid invitation.")

    def test_non_admin_member_cannot_invite(self):
        regular_user = G(User)
        G(
            ProjectMember,
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
        self.assertEqual(data["errors"]["detail"], "Admin rights required.")

    @patch("core.services.JiraProjectService.add_user_to_jira_project")
    def test_accept_invitation_idempotency(self, mock_jira_sync):
        invitation = G(
            ProjectInvitation,
            project=self.project,
            invitee=self.invitee,
            invited_by=self.user,
            is_admin=True,
            is_accepted=False,
            expires_at=timezone.now() + timedelta(days=7),
        )

        self.client.force_authenticate(user=self.invitee)
        url = reverse("accept-invitation", kwargs={"token": invitation.token})

        response1 = self.client.post(url)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

        response2 = self.client.post(url)
        data2 = self.get_json_data(response2)

        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(data2["message"], "Invalid token")

        self.assertEqual(mock_jira_sync.call_count, 1)


class ProjectMemberAPITests(APITestCase):
    def setUp(self):
        self.owner = G(User, email="owner@test.com")
        self.admin = G(User, email="admin@test.com")
        self.member = G(User, email="member@test.com")

        self.project = G(
            ProjectModel,
            jira_project_key="MEM",
            owner=self.owner,
        )

        G(ProjectMember, project=self.project, user=self.owner, is_admin=True)
        self.admin_membership = G(
            ProjectMember, project=self.project, user=self.admin, is_admin=True
        )
        self.member_membership = G(
            ProjectMember, project=self.project, user=self.member, is_admin=False
        )

        self.list_url = reverse(
            "project-member-list", kwargs={"project_id": self.project.id}
        )

        self.get_role_url = lambda uid: reverse(
            "project-member-role",
            kwargs={"project_id": self.project.id, "user_id": uid},
        )

    def test_list_members_ordering(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            str(response.data["results"][0]["user_id"]), str(self.member.user_id)
        )

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_promote_member_to_admin_by_owner(self, mockjira):
        self.client.force_authenticate(user=self.owner)
        url = self.get_role_url(self.member.user_id)

        response = self.client.patch(url, {"role": "admin"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.member_membership.refresh_from_db()
        self.assertTrue(self.member_membership.is_admin)

    def test_member_cannot_promote_others(self):
        self.client.force_authenticate(user=self.member)
        url = self.get_role_url(self.admin.user_id)

        response = self.client.patch(url, {"role": "member"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_transfer_ownership_flow(self, mock_jira):
        self.client.force_authenticate(user=self.owner)
        url = self.get_role_url(self.admin.user_id)

        response = self.client.patch(url, {"role": "owner"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.project.refresh_from_db()
        self.assertEqual(self.project.owner, self.admin)

        prev_owner_mem = ProjectMember.objects.get(
            user=self.owner, project=self.project
        )
        self.assertTrue(prev_owner_mem.is_admin)

    def test_owner_cannot_leave_without_transfer(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse(
            "project-member-remove",
            kwargs={"project_id": self.project.id, "user_id": self.owner.user_id},
        )

        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertEqual(
            data["message"],
            "Owner cannot leave without transferring ownership.",
        )

    @patch("core.services.JiraProjectService.remove_user_from_jira_project")
    def test_kick_member_success(self, mock_jira):
        self.client.force_authenticate(user=self.admin)
        url = reverse(
            "project-member-remove",
            kwargs={"project_id": self.project.id, "user_id": self.member.user_id},
        )

        response = self.client.patch(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ProjectMember.objects.filter(
                user=self.member, status=MemberStatus.MEMBER
            ).exists()
        )

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_admin_can_promote_member_to_admin(self, mock_jira):
        self.client.force_authenticate(user=self.admin)
        url = self.get_role_url(self.member.user_id)

        response = self.client.patch(url, {"projectRole": "admin"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_membership.refresh_from_db()
        self.assertTrue(self.member_membership.is_admin)

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_owner_can_demote_admin_to_member(self, mock_jira):
        self.client.force_authenticate(user=self.owner)
        url = self.get_role_url(self.admin.user_id)

        response = self.client.patch(url, {"projectRole": "member"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin_membership.refresh_from_db()
        self.assertFalse(self.admin_membership.is_admin)

    @patch("core.services.JiraProjectService.update_user_role_in_jira")
    def test_admin_cannot_demote_other_admins(self, mock_jira):
        admin2 = G(User)
        G(ProjectMember, project=self.project, user=admin2, is_admin=True)

        self.client.force_authenticate(user=self.admin)
        url = self.get_role_url(admin2.user_id)

        response = self.client.patch(url, {"projectRole": "member"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("core.services.JiraProjectService.remove_user_from_jira_project")
    def test_member_can_leave_project_voluntarily(self, mock):
        self.client.force_authenticate(user=self.member)
        url = reverse(
            "project-member-remove",
            kwargs={"project_id": self.project.id, "user_id": self.member.user_id},
        )

        response = self.client.patch(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ProjectMember.objects.filter(
                user=self.member, project=self.project, status=MemberStatus.MEMBER
            ).exists()
        )
