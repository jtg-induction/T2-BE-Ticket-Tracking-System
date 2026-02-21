from django.conf import settings
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import CustomUser
from .serializers import (
    CustomTokenObtainPairSerializer,
    SignupLinkRequestSerializer,
    UserSerializer,
)
from .utils import (
    clear_auth_cookie,
    generate_signup_jwt,
    send_registration_email,
    set_auth_cookie,
)


class UserViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for managing CustomUser CRUD operations.

    Provides endpoints for listing, retrieving, updating, and creating users.
    """

    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    lookup_field = "user_id"
    pagination_class = PageNumberPagination

    def get_object(self):
        """
        Returns the object the view is displaying.

        If 'user_id' is not provided in the URL, it defaults to returning
        the currently authenticated user.

        Returns:
            CustomUser: The user instance retrieved via lookup_field or current session.
        """
        if "user_id" not in self.kwargs:
            return self.request.user
        return super().get_object()

    def get_serializer_context(self):
        """
        Extra context provided to the serializer class.

        Returns:
            dict: updated context
        """
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def get_permissions(self):
        """
        Returns the list of permissions that this view requires.
        """
        if self.action == "create":
            return [permissions.AllowAny()]

        if self.action == "list":
            return [permissions.IsAdminUser()]

        return [permissions.IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        """
        Handles user registration.

        Returns:
            Response: User data and access token with a 201 status.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        token_serializer = CustomTokenObtainPairSerializer()
        tokens = token_serializer.get_token(user)

        response_data = {
            "access": str(tokens.access_token),
            "user": UserSerializer(user).data,
        }

        response = Response(response_data, status=status.HTTP_201_CREATED)
        set_auth_cookie(response, str(tokens))

        return response


class CustomLoginView(TokenObtainPairView):
    """
    View to handle user login and JWT issuance.
    """

    def post(self, request, *args, **kwargs):
        """
        Authenticates user credentials and returns an access token.

        Args:
            request: The HTTP request containing login credentials.

        Returns:
            Response: Access token in the body and refresh token in a secure cookie.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tokens = serializer.validated_data
        access_token = tokens.get("access")
        refresh_token = tokens.get("refresh")
        response = Response({"access": access_token}, status=status.HTTP_200_OK)
        set_auth_cookie(response, refresh_token)

        return response


class LogoutView(APIView):
    """
    View to handle log out by clearing the authentication cookie.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """
        Logs out user and blacklists refresh token.

        Args:
            request (Request): The HTTP request object containing the refresh token in COOKIES.

        Returns: 'Set-Cookie' header with an expired date to clear the authentication cookie.
        """
        response = Response(
            {"message": "Successfully logged out"}, status=status.HTTP_200_OK
        )
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE"])
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass
        clear_auth_cookie(response)

        return response


class CustomTokenRefreshView(TokenRefreshView):
    """
    View to handle refresh token rotation
    """

    def post(self, request):
        """
        Clears the auth cookie from the response.

        Returns:
            Response: Success message with a 200 status.
        """
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE"])

        if not refresh_token:
            return Response(
                {"detail": "Refresh token missing."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = self.get_serializer(data={"refresh": refresh_token})

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

        tokens = serializer.validated_data
        response = Response({"access": tokens.get("access")}, status=status.HTTP_200_OK)

        new_refresh = tokens.get("refresh")
        if new_refresh:
            set_auth_cookie(response, new_refresh)

        return response


class RequestSignupLinkView(GenericAPIView):
    """
    Handles requests for registration signup links.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = SignupLinkRequestSerializer

    def post(self, request):
        """
        Generates a signup JWT and sends it via email.

        Returns:
            Response: Success message or 500 status if email delivery fails.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        token = generate_signup_jwt(email)
        signup_url = f"{settings.SIGNUP_URL}?token={token}"

        try:
            send_registration_email(email, signup_url)
        except Exception:
            return Response(
                {"message": "Failed to send email: Some error occured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"message": "Verification link has been sent to your email."},
            status=status.HTTP_200_OK,
        )
