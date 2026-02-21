from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProjectInvitationView, ProjectMemberViewSet, ProjectViewSet

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
    path(
        "project/<uuid:project_id>/members/",
        ProjectMemberViewSet.as_view({"get": "list"}),
        name="project-member-list",
    ),
    path(
        "project/<uuid:project_id>/members/<uuid:user_id>/role/",
        ProjectMemberViewSet.as_view({"post": "update_role"}),
        name="project-member-role",
    ),
    path(
        "project/<uuid:project_id>/members/<uuid:user_id>/",
        ProjectMemberViewSet.as_view({"post": "destroy"}),
        name="project-member-remove",
    ),
]
