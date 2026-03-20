from django.urls import include, path
from rest_framework.routers import DefaultRouter

from project.views import ProjectInvitationView, ProjectMemberViewSet, ProjectViewSet

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
    path(
        "<uuid:project_id>/members/",
        include(
            [
                path(
                    "",
                    ProjectMemberViewSet.as_view({"get": "list"}),
                    name="project-member-list",
                ),
                path(
                    "list-all-users/",
                    ProjectMemberViewSet.as_view({"get": "list_all_users"}),
                    name="project-list-all-users",
                ),
                path(
                    "<uuid:user_id>/role/",
                    ProjectMemberViewSet.as_view({"patch": "update_role"}),
                    name="project-member-role",
                ),
                path(
                    "<uuid:user_id>/",
                    ProjectMemberViewSet.as_view({"patch": "remove_user"}),
                    name="project-member-remove",
                ),
            ]
        ),
    ),
]
