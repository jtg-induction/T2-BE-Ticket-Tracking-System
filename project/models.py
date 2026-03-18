import secrets
import uuid

from django.conf import settings
from django.db import models, transaction
from django.db.models import UniqueConstraint
from django.utils import timezone

from core.models import BaseModel, SoftDeleteManager

from .enums import MemberStatus


class ProjectManager(SoftDeleteManager):
    """
    Custom Manager for ProjectModel handling soft deletes and initialization.
    """

    def create_with_user(self, user, **project_data):
        """
        A helper method to set the owner, created_by, and updated_by to the requesting user automatically.

        :param user: The user instance (usually request.user)
        :param project_data: Dictionary of project fields
        """
        with transaction.atomic():
            project = self.create(owner=user, updated_by=user, **project_data)
            ProjectMember.objects.create(
                project=project, user=user, is_admin=True, updated_by=user
            )
            return project


class ProjectMember(BaseModel):
    """
    Through model representing the membership of a user in a project.

    Stores role-based permissions (is_admin) and participation status.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "ProjectModel", on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_memberships",
    )
    is_admin = models.BooleanField(default=False)
    status = models.CharField(
        choices=MemberStatus.choices, default=MemberStatus.MEMBER, max_length=10
    )

    constraints = [
        models.UniqueConstraint(
            fields=["project", "user"],
            name="unique_project_membership",
            violation_error_message="User is already in this project.",
        )
    ]


class ProjectModel(BaseModel):
    """
    Represents a Jira Project instance linked to a specific Atlassian Site URL.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    jira_id = models.CharField(max_length=50, db_index=True)
    jira_project_key = models.CharField(max_length=10, null=False)
    site_url = models.URLField(null=False)
    is_archived = models.BooleanField(default=False)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_projects",
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through=ProjectMember,
        through_fields=("project", "user"),
        related_name="joined_projects",
    )

    objects = ProjectManager()

    class Meta:
        verbose_name = "Jira Project"
        ordering = ["-created_at"]
        unique_together = (("jira_project_key", "site_url"),)

    def __str__(self):
        return f"{self.jira_project_key} - {self.title}"


class ProjectInvitation(BaseModel):
    """
    Model representing a pending request for a user to join a project.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "ProjectModel", on_delete=models.CASCADE, related_name="invitations"
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_invitations",
    )
    is_admin = models.BooleanField(default=False)
    token = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_invitations",
    )
    expires_at = models.DateTimeField()
    is_accepted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        """
        Overrides the save method to initialize default invitation metadata.

        - Generates a cryptographically secure URL-safe token if not provided.
        - Sets a default expiration date of 7 days from the creation time.
        """
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """
        Checks if the invitation is currently valid.

        Returns:
            bool: True if the invitation has not been accepted and is not past
                  its expiration date.
        """
        return not self.is_accepted and self.expires_at > timezone.now()

    class Meta:
        """
        No new invitation is sent until the previous one expires
        """

        constraints = [
            UniqueConstraint(
                fields=["project", "invitee", "is_deleted"],
                name="unique_active_invite_per_project_invitee",
                violation_error_message="An active invitation already exists",
            )
        ]
