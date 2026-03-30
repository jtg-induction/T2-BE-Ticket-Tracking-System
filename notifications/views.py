from rest_framework import status, viewsets
from rest_framework.response import Response

from notifications.constants import NotificationMessages
from notifications.models import Notifications
from notifications.serializers import SubscriptionSerializer
from ticket.models import Ticket


class TicketViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing subscription-related actions on tickets.
    """

    queryset = Ticket.objects.all()
    serializer_class = SubscriptionSerializer
    lookup_url_kwarg = "ticket_id"

    def subscribe(self, request, ticket_id=None):
        """
        Subscribes the authenticated user to a specific ticket.
        """
        ticket = self.get_object()

        serializer = self.get_serializer(
            data=request.data, context={"request": request, "ticket": ticket}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def unsubscribe(self, request, ticket_id=None):
        """
        Removes the authenticated user's subscription from a specific ticket.
        """
        ticket = self.get_object()

        deleted, _ = Notifications.objects.filter(
            ticket=ticket, subscriber=request.user
        ).delete()

        if not deleted:
            return Response(
                {"detail": NotificationMessages.NOT_SUBSCRIBED},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
