from django.urls import path
from rest_framework import routers

from .views import (
    CustomLoginView,
    CustomTokenRefreshView,
    LogoutView,
    RequestSignupLinkView,
    UserViewSet,
)

router = routers.SimpleRouter()
router.register("user", UserViewSet, basename="user-profile")

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="token_obtain_pair"),
    path("request-link/", RequestSignupLinkView.as_view(), name="request-signup-link"),
    path("login/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
]

urlpatterns += router.urls
