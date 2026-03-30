from django.urls import include, path
from rest_framework.routers import DefaultRouter

from project.views import ProjectInvitationView, ProjectViewSet

router = DefaultRouter()
router.register(r"", ProjectViewSet, basename="project")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "<uuid:pk>/invite/",
        ProjectInvitationView.as_view({"post": "invite"}),
        name="project-invite",
    ),
    path(
        "accept-invite/<str:token>/",
        ProjectInvitationView.as_view({"post": "accept"}),
        name="accept-invitation",
    ),
    path(
        "reject-invite/<str:token>/",
        ProjectInvitationView.as_view({"delete": "reject"}),
        name="reject-invitation",
    ),
    path("<uuid:project_id>/", include("project.urls.urls_dependent")),
]
