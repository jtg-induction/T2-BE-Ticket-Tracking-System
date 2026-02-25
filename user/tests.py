import uuid
from django.urls import reverse
from django.core import mail
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase
from user.models import CustomUser
from user.utils import generate_signup_jwt

class AuthFlowTests(APITestCase):
    """
    Tests authentication, registration, and token management.
    """

    def setUp(self):
        """
        Initialize test URLs and settings.
        """
        self.request_link_url = reverse('request-signup-link')
        self.signup_url = reverse('user-profile-list')
        self.login_url = reverse('token_obtain_pair')
        self.refresh_url = reverse('token_refresh')
        self.cookie_name = settings.SIMPLE_JWT.get('AUTH_COOKIE', 'refresh_token')

    def create_user(self, email, password="password123", **extra_fields):
        """
        Helper to create a user instance.
        """
        if 'jira_id' not in extra_fields:
            extra_fields['jira_id'] = f"JIRA-{uuid.uuid4().hex[:8]}"
        
        if 'jira_api_token' not in extra_fields:
            extra_fields['jira_api_token'] = f"JIRA-{uuid.uuid4().hex[:8]}"

        return CustomUser.objects.create_user(
            email=email,
            password=password,
            **extra_fields
        )

    def test_request_link_success(self):
        """
        Verify successful signup link request sends an email.
        """
        response = self.client.post(self.request_link_url, {"email": "new_user@example.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verification link", response.data['message'])

    def test_request_link_fails_if_user_exists(self):
        """
        Verify link request fails for existing email addresses.
        """
        email = "already_here@example.com"
        self.create_user(email=email)
        response = self.client.post(self.request_link_url, {"email": email})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("exists", str(response.data))

    def test_signup_success(self):
        """
        Verify registration via JWT token creates a user.
        """
        email = "verify@example.com"
        token = generate_signup_jwt(email)
        data = {
            "token": token,
            "password": "securepassword",
            "first_name": "Test",
            "last_name": "User",
            "jira_id": "76341809",
            "jira_api_token": "some_token"
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(CustomUser.objects.filter(email=email).exists())

    def test_signup_fails_with_fake_token(self):
        """
        Verify registration fails with malformed or invalid tokens.
        """
        data = {
            "token": "completely.fake.token",
            "password": "password123",
            "first_name": "Test",
            "last_name": "User",
            "jira_id": "76341809",
            "jira_api_token": "some_token"
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", response.data)

    def test_login_returns_custom_payload(self):
        """
        Verify login returns access token and hides refresh token from body.
        """
        email = "login@example.com"
        password = "correct_password"
        self.create_user(email=email, password=password)
        response = self.client.post(self.login_url, {"email": email, "password": password})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_login_fails_wrong_password(self):
        """
        Verify login fails with invalid password.
        """
        email = "login@example.com"
        self.create_user(email=email, password="correct_password")
        response = self.client.post(self.login_url, {"email": email, "password": "wrong_password"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_generation(self):
        """
        Verify access token refresh using HttpOnly cookie.
        """
        email = "refresh@example.com"
        password = "password123"
        self.create_user(email=email, password=password)
        login_res = self.client.post(self.login_url, {"email": email, "password": password})
        self.assertIn(self.cookie_name, login_res.cookies)
        response = self.client.post(self.refresh_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn(self.cookie_name, response.cookies)
