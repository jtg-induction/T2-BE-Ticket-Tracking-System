from django.urls import path

from ticket.views import JiraTicketViewSet, TicketViewSet

urlpatterns = [
    path(
        "project/<uuid:project_pk>/ticket/",
        TicketViewSet.as_view({"get": "list", "post": "create"}),
        name="ticket-list",
    ),
    path(
        "project/<uuid:project_pk>/ticket/<uuid:pk>/",
        TicketViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="ticket-detail",
    ),
    path(
        "ticket/",
        TicketViewSet.as_view({"get": "list_all_tickets"}),
        name="my-tickets",
    ),
    path(
        "project/<uuid:project_pk>/jql/ticket/",
        JiraTicketViewSet.as_view({"get": "search", "post": "import_to_local"}),
        name="jql-ticket",
    ),
]
