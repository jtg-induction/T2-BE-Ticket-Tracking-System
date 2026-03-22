from django.urls import path

from .views import CommentViewSet

urlpatterns = [
    path(
        "ticket/<uuid:ticket_pk>/comment/",
        CommentViewSet.as_view({"get": "list", "post": "create"}),
        name="ticket-comment-list",
    ),
    path(
        "ticket/<uuid:ticket_pk>/comment/<uuid:pk>/",
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
