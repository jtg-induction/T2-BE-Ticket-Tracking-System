import base64

from ddf import G
from django.conf import settings
from django.urls import reverse
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
        self.request_link_url = reverse("request-signup-link")
        self.signup_url = reverse("user-me")
        self.login_url = reverse("token_obtain_pair")
        self.refresh_url = reverse("token_refresh")
        self.cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "refresh_token")

    def _encode_password(self, password):
        """
        Helper to Base64 encode passwords to match CustomTokenObtainPairSerializer requirements.
        """
        return base64.b64encode(password.encode("utf-8")).decode("utf-8")

    def test_request_link_success(self):
        """
        Verify successful signup link request sends an email.
        """
        response = self.client.post(
            self.request_link_url, {"email": "new_user@example.com"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Verification link", response.data["message"])

    def test_request_link_fails_if_user_exists(self):
        """
        Verify link request fails for existing email addresses.
        """
        email = "already_here@example.com"
        G(CustomUser, email=email)
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
            "jira_api_token": "some_token",
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
            "jira_api_token": "some_token",
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
        user = G(CustomUser, email=email, jira_id="JIRA-123")
        user.set_password(password)
        user.save()

        encoded_password = self._encode_password(password)
        response = self.client.post(
            self.login_url, {"email": email, "password": encoded_password}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_login_fails_wrong_password(self):
        """
        Verify login fails with invalid password.
        """
        email = "login@example.com"
        user = G(CustomUser, email=email)
        user.set_password("correct_password")
        user.save()

        encoded_password = self._encode_password("wrong_password")
        response = self.client.post(
            self.login_url, {"email": email, "password": encoded_password}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_clears_cookie(self):
        """
        Verify logout clears the refresh token cookie.
        """
        email = "logout_test@example.com"
        password = "password123"
        user = G(CustomUser, email=email, jira_id="JIRA-LOGOUT")
        user.set_password(password)
        user.save()

        encoded_password = self._encode_password(password)
        login_res = self.client.post(
            self.login_url, {"email": email, "password": encoded_password}
        )
        access_token = login_res.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        logout_url = reverse("logout")
        response = self.client.post(logout_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        target_cookie = response.cookies.get(self.cookie_name)
        self.assertEqual(target_cookie.value, "")
        self.assertEqual(target_cookie["max-age"], 0)
        self.assertTrue(target_cookie["expires"].endswith("GMT"))
