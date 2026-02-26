from django.conf import settings
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .serializers import SignupLinkRequestSerializer, UserSerializer
from .utils import generate_signup_jwt, send_registration_email

class UserViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    ViewSet for CRUD user.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'user_id'
    pagination_class = PageNumberPagination

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]

        return [permissions.IsAuthenticated()]


class CustomLoginView(TokenObtainPairView):
    """
    View to handle login
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            refresh_token = response.data.pop('refresh')

            response.set_cookie(
                key=settings.SIMPLE_JWT['AUTH_COOKIE'],
                value=refresh_token,
                max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
                secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE'],
                path='/api/',
            )
        return response


class LogoutView(APIView):
    """
    View to handle log out
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        response = Response(
            {"message": "Successfully logged out"},
            status=status.HTTP_200_OK
        )

        response.delete_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE'],
            path=settings.SIMPLE_JWT.get('AUTH_COOKIE_PATH', '/api/'),
            samesite=settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE', 'Lax')
        )
        
        return response


class CustomTokenRefreshView(TokenRefreshView):
    """
    View to handle refresh token rotation
    """
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE'])

        if refresh_token:
            data = dict(request.data)
            data['refresh'] = refresh_token
            request._full_data = data

        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            if 'refresh' in response.data:
                new_refresh_token = response.data.pop('refresh')
                response.set_cookie(
                    key=settings.SIMPLE_JWT['AUTH_COOKIE'],
                    value=new_refresh_token,
                    max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
                    secure=settings.SIMPLE_JWT.get('AUTH_COOKIE_SECURE', False),
                    httponly=settings.SIMPLE_JWT.get('AUTH_COOKIE_HTTP_ONLY', True),
                    samesite=settings.SIMPLE_JWT.get('AUTH_COOKIE_SAMESITE', 'Lax'),
                    path=settings.SIMPLE_JWT.get('AUTH_COOKIE_PATH', '/api/'),
                )
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

        email = serializer.validated_data['email']
        token = generate_signup_jwt(email)

        signup_url = f"{settings.SIGNUP_URL}?token={token}"

        try:
            send_registration_email(email, signup_url)
        except Exception as e:
            return Response(
                {"message": "Failed to send email: Some error occured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({
            "message": "Verification link has been sent to your email."
        }, status=status.HTTP_200_OK)
