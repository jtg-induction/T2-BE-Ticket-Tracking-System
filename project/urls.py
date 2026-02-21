from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AcceptInvitationView,
    ProjectViewSet,
    RejectInvitationView,
)

router = DefaultRouter()
router.register(r"project", ProjectViewSet, basename="project")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "project/accept-invite/<str:token>/",
        AcceptInvitationView.as_view(),
        name="accept-invitation",
    ),
    path(
        "project/reject-invite/<str:token>/",
        RejectInvitationView.as_view(),
        name="reject-invitation",
    ),
]
