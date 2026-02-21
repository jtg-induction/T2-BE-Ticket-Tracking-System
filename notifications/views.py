from rest_framework import status, viewsets
from rest_framework.response import Response

from ticket.models import Ticket

from .models import Notifications
from .serializers import SubscriptionSerializer


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = SubscriptionSerializer
    lookup_url_kwarg = "ticket_id"

    def subscribe(self, request, ticket_id=None):
        ticket = self.get_object()

        obj, created = Notifications.objects.get_or_create(
            ticket=ticket, subscriber=request.user
        )

        if not created:
            return Response(
                {"detail": "Already subscribed."}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def unsubscribe(self, request, ticket_id=None):
        ticket = self.get_object()

        deleted_count, _ = Notifications.objects.filter(
            ticket=ticket, subscriber=request.user
        ).delete()

        if deleted_count == 0:
            return Response(
                {"detail": "Not subscribed."}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
