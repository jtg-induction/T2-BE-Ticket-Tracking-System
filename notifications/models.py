import uuid

from django.conf import settings
from django.db import models

from core.models import BaseModel
from ticket.models import Ticket


class Notifications(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="notifications"
    )
    subscriber = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
