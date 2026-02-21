import uuid

from django.conf import settings
from django.db import models

from core.models import BaseModel
from project.models import ProjectModel

from .enums import Category, Priority, Status


class Ticket(BaseModel):
    """
    Represents a task or issue synchronized between the local system and Jira.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jira_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, max_length=255)

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_tickets",
    )

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
    )

    project = models.ForeignKey(
        ProjectModel,
        on_delete=models.CASCADE,
        related_name="tickets",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM
    )
    category = models.CharField(max_length=50, choices=Category.choices, null=True)

    status_updated_at = models.DateTimeField(null=True, blank=True)
    status_updated_from = models.CharField(
        max_length=20, choices=Status.choices, null=True, blank=True
    )
    status_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_updates",
    )

    deadline = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    deadline_task_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.jira_id or 'No Jira ID'})"
