from rest_framework import serializers

from notifications.constants import NotificationMessages
from notifications.models import Notifications


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for handling ticket subscriptions.
    """

    class Meta:
        model = Notifications
        fields = ["id", "ticket", "subscriber", "created_at"]
        read_only_fields = ["id", "ticket", "subscriber", "created_at"]

    def validate(self, attrs):
        """
        Validates that a user isn't already subscribed to the specific ticket.
        """
        ticket = self.context.get("ticket")
        user = self.context.get("request").user

        if Notifications.objects.filter(ticket=ticket, subscriber=user).exists():
            raise serializers.ValidationError(
                {"detail": NotificationMessages.ALREADY_SUBSCRIBED}
            )

        return attrs

    def create(self, validated_data):
        """
        Creates a new subscription link between the user and the ticket.
        """
        return Notifications.objects.create(
            ticket=self.context.get("ticket"),
            subscriber=self.context.get("request").user,
        )
