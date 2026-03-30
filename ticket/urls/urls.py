from django.urls import include, path

from ticket.views import TicketViewSet

urlpatterns = [
    path(
        "ticket/", TicketViewSet.as_view({"get": "list_all_tickets"}), name="my-tickets"
    ),
    path("ticket/<uuid:ticket_pk>/", include("comment.urls.urls_dependent")),
]
