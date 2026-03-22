from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.response import Response

from project.enums import MemberStatus
from ticket.models import Ticket

from .models import Notifications
from .serializers import SubscriptionSerializer


class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = SubscriptionSerializer
    lookup_url_kwarg = "ticket_id"

    def get_queryset(self):
        """
        Restrict tickets to only those where the user is a project member,
        the reporter, or the assignee.
        """
        user = self.request.user
        return Ticket.objects.filter(
            Q(
                project__memberships__user=user,
                project__memberships__status=MemberStatus.MEMBER,
            )
            | Q(reporter=user)
            | Q(assignee=user)
        ).distinct()

    def subscribe(self, request, ticket_id=None):
        ticket = self.get_object()

        obj, created = Notifications.objects.get_or_create(
            ticket=ticket, subscriber=request.user
        )

        if not created:
            return Response(
                {"detail": "Already subscribed."}, status=status.HTTP_400_BAD_REQUEST
            )

        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK

        serializer = self.get_serializer(obj)
        return Response(serializer.data, status=status_code)

    def unsubscribe(self, request, ticket_id=None):
        ticket = self.get_object()

        deleted_count, _ = Notifications.objects.filter(
            ticket=ticket, subscriber=request.user
        ).delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
