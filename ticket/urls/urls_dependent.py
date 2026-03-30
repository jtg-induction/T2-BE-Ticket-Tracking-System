from django.urls import include, path

from ticket.views import JiraTicketViewSet, TicketViewSet

urlpatterns = [
    path(
        "ticket/",
        TicketViewSet.as_view({"get": "list", "post": "create"}),
        name="ticket-list",
    ),
    path(
        "ticket/<uuid:pk>/",
        include(
            [
                path(
                    "",
                    TicketViewSet.as_view(
                        {
                            "get": "retrieve",
                            "patch": "partial_update",
                            "delete": "destroy",
                        }
                    ),
                    name="ticket-detail",
                ),
            ]
        ),
    ),
    path(
        "jql/ticket/",
        JiraTicketViewSet.as_view({"get": "search", "post": "import_to_local"}),
        name="jql-ticket",
    ),
]
