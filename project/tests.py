import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ProjectModel

User = get_user_model()


class ProjectAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123",
            jira_id="JIRA-USER-123",
            jira_api_token="mock-api-token",
        )
        self.client.force_authenticate(user=self.user)
        self.list_create_url = reverse("project-list")

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
        self.assertEqual(data["meta"]["count"], 3)
        self.assertIsInstance(data["data"], list)
        self.assertEqual(len(data["data"]), 3)

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
