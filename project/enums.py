from django.db import models


class MemberStatus(models.TextChoices):
    """
    Represents the status of member in specific project
    """

    INVITED = "invited", "Invited"
    MEMBER = "member", "Member"
    LEFT = "left", "Left"
