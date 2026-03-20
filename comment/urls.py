from django.urls import include, path

from comment.views import CommentViewSet

urlpatterns = [
    path(
        "ticket/<uuid:ticket_pk>/",
        include(
            [
                path(
                    "comment/",
                    CommentViewSet.as_view({"get": "list", "post": "create"}),
                    name="ticket-comment-list",
                ),
                path(
                    "<uuid:pk>/",
                    CommentViewSet.as_view(
                        {
                            "get": "retrieve",
                            "put": "update",
                            "patch": "partial_update",
                            "delete": "destroy",
                        }
                    ),
                    name="ticket-comment-detail",
                ),
            ]
        ),
    ),
]
