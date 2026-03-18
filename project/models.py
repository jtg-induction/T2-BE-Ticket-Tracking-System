import uuid

from django.conf import settings
from django.db import models, transaction

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

    class Meta:
        unique_together = ("project", "user")


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
