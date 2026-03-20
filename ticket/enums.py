from django.db import models


class Status(models.TextChoices):
    """
    Defines the workflow states for a Ticket.
    """

    TODO = "To Do", "To Do"
    IN_PROGRESS = "In Progress", "In Progress"
    DONE = "Done", "Done"
    CLOSED = "Closed", "Closed"


class Priority(models.TextChoices):
    """
    Defines the urgency levels for a Ticket.
    """

    HIGHEST = "Highest", "Highest"
    HIGH = "High", "High"
    MEDIUM = "Medium", "Medium"
    LOW = "Low", "Low"
    LOWEST = "Lowest", "Lowest"


class Category(models.TextChoices):
    """
    Defines the functional domain of a Ticket.
    """

    DEVELOPMENT = "Development", "Development"
    DESIGN = "Design", "Design"
    QA = "QA", "QA"
    RESEARCH = "Research", "Research"
