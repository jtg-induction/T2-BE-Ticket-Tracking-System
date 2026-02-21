import uuid

from django.conf import settings
from django.db import models

from core.models import BaseModel
from ticket.models import Ticket


class CommentModel(BaseModel):
    """
    Represents a discussion entry associated with a specific Ticket.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jira_id = models.CharField(null=True)
    message = models.TextField(max_length=10000)
    commentator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="commentator",
        null=True,
    )
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comment")
    external_author_name = models.CharField(max_length=255, null=True, blank=True)
