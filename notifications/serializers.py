from rest_framework import serializers

from notifications.models import Notifications


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notifications
        fields = ["id", "ticket", "subscriber", "created_at"]
        read_only_fields = ["id", "ticket", "subscriber", "created_at"]
