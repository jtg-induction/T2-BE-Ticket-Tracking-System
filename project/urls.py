from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProjectInvitationView, ProjectViewSet

router = DefaultRouter()
router.register(r"project", ProjectViewSet, basename="project")


urlpatterns = [
    path("", include(router.urls)),
    path(
        "project/<uuid:pk>/invite/",
        ProjectInvitationView.as_view({"post": "invite"}),
        name="project-invite",
    ),
    path(
        "project/accept-invite/<str:token>/",
        ProjectInvitationView.as_view({"post": "accept"}),
        name="accept-invitation",
    ),
    path(
        "project/reject-invite/<str:token>/",
        ProjectInvitationView.as_view({"post": "reject"}),
        name="reject-invitation",
    ),
]
