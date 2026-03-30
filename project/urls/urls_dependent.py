from django.urls import include, path

from project.views import ProjectMemberViewSet

urlpatterns = [
    # Project Members
    path(
        "members/",
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
    path("", include("ticket.urls.urls_dependent")),
]
