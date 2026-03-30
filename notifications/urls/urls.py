from django.urls import path

from notifications.views import TicketViewSet

urlpatterns = [
    path(
        "tickets/<uuid:ticket_id>/subscribe/",
        TicketViewSet.as_view({"post": "subscribe"}),
        name="ticket-subscribe",
    ),
    path(
        "tickets/<uuid:ticket_id>/unsubscribe/",
        TicketViewSet.as_view({"delete": "unsubscribe"}),
        name="ticket-unsubscribe",
    ),
]
