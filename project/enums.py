from django.db import models


class MemberStatus(models.TextChoices):
    """
    Represents the status of member in specific project
    """

    INVITED = "invited", "Invited"
    MEMBER = "member", "Member"
    LEFT = "left", "Left"


class ProjectRole(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MEMBER = "member", "Member"


class JiraRole(models.TextChoices):
    """Specific role names expected by the Jira Cloud API."""

    ADMINISTRATOR = "Administrator", "Administrator"
    MEMBER = "Member", "Member"
