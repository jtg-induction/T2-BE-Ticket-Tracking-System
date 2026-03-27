from django.db import models


class MemberStatus(models.TextChoices):
    """
    Represents the status of member in specific project
    """

    INVITED = "invited", "Invited"
    MEMBER = "member", "Member"
    LEFT = "left", "Left"


class ProjectRole(models.TextChoices):
    """
    Roles within a project context.
    """

    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MEMBER = "member", "Member"
