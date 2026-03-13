import uuid

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import CustomUser


class UserAPITests(APITestCase):
    """
    Test User Profile API and field restrictions.
    """

    def setUp(self):
        """
        Setup test users and URLs.
        """
        self.user_data = {
            "email": "anmol@example.com",
            "password": "password123",
            "jira_id": "JIRA-123",
            "first_name": "Anmol",
            "last_name": "S",
            "jira_api_token": "sometoken",
        }
        self.other_user_data = {
            "email": "other@example.com",
            "password": "password123",
            "jira_id": "JIRA-456",
            "first_name": "Other",
            "jira_api_token": "sometoken123",
            "last_name": "User",
        }
        self.user = CustomUser.objects.create_user(**self.user_data)
        self.other_user = CustomUser.objects.create_user(**self.other_user_data)

        self.me_url = reverse("user-me")
        self.detail_url = lambda uid: reverse("user-detail", kwargs={"user_id": uid})

    def authenticate(self, user):
        """
        Authenticate a user.
        """
        self.client.force_authenticate(user=user)

    def test_get_own_profile_singular_endpoint(self):
        """
        Test retrieving own profile via base endpoint.
        """
        self.authenticate(self.user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertTrue(response.data["can_edit"])

    def test_get_own_profile_via_id(self):
        """
        Test canEdit flag on own profile via ID.
        """
        self.authenticate(self.user)
        url = self.detail_url(self.user.user_id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["can_edit"])

    def test_get_other_user_profile(self):
        """
        Test canEdit is false for other users.
        """
        self.authenticate(self.user)
        url = self.detail_url(self.other_user.user_id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_edit"])

    def test_update_allowed_fields(self):
        """
        Test updating permitted fields.
        """
        self.authenticate(self.user)
        data = {"first_name": "NewName"}
        response = self.client.patch(self.me_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "NewName")

    def test_update_jira_id_fails(self):
        """
        Test jira_id update restriction.
        """
        self.authenticate(self.user)
        data = {"jira_id": "HACKED-ID"}
        response = self.client.patch(self.me_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("jira_id", response.data)

    def test_update_email_fails(self):
        """
        Test email update restriction.
        """
        self.authenticate(self.user)
        data = {"email": "newemail@example.com"}
        response = self.client.patch(self.me_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_update_user_id_ignored(self):
        """
        Test user_id read-only restriction.
        """
        old_id = self.user.user_id
        self.authenticate(self.user)
        data = {"user_id": uuid.uuid4()}
        response = self.client.patch(self.me_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(uuid.UUID(str(response.data["user_id"])), old_id)

    def test_delete_user_fails(self):
        """
        Test deletion restriction.
        """
        self.authenticate(self.user)
        response = self.client.delete(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unauthenticated_access(self):
        """
        Test access without authentication.
        """
        self.client.logout()
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_nonexistent_uuid(self):
        """
        Test 404 for missing UUID.
        """
        self.authenticate(self.user)
        url = self.detail_url(uuid.uuid4())
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
