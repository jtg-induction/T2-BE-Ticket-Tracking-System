from django.conf import settings
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import CustomUser
from .serializers import SignupLinkRequestSerializer, UserSerializer
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
    ViewSet for CRUD user.
    """

    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    lookup_field = "user_id"
    pagination_class = PageNumberPagination

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]

        return [permissions.IsAuthenticated()]


class CustomLoginView(TokenObtainPairView):
    """
    View to handle login
    """

    def post(self, request, *args, **kwargs):
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
        response = Response(
            {"message": "Successfully logged out"}, status=status.HTTP_200_OK
        )
        clear_auth_cookie(response)

        return response


class CustomTokenRefreshView(TokenRefreshView):
    """
    View to handle refresh token rotation
    """

    def post(self, request):
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
    Caters the signup url request
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = SignupLinkRequestSerializer

    def post(self, request):
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
