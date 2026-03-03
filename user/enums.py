from django.db import models


class Roles(models.TextChoices):
    """
    Enum to choose between different roles
    """

    software_dev = "SD", "Software Developer"
    senior_software_dev = "SSD", "Senior Software Developer"
    quality_analyst = "QA", "Quality Analyst"
    manager = "M", "manager"
    designer = "DG", "designer"
