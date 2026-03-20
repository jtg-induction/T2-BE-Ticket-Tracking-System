from django.urls import path

from user.views import (
    CustomLoginView,
    CustomTokenRefreshView,
    LogoutView,
    RequestSignupLinkView,
    UserViewSet,
)

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="token_obtain_pair"),
    path("request-link/", RequestSignupLinkView.as_view(), name="request-signup-link"),
    path("login/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "user/<uuid:user_id>/",
        UserViewSet.as_view(
            {
                "get": "retrieve",
            }
        ),
        name="user-detail",
    ),
    path(
        "user/",
        UserViewSet.as_view(
            {
                "get": "retrieve",
                "post": "create",
                "put": "update",
                "patch": "partial_update",
            }
        ),
        name="user-me",
    ),
]
