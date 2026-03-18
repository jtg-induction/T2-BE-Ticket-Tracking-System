from django.contrib import admin

from .models import ProjectModel


@admin.register(ProjectModel)
class ProjectAdmin(admin.ModelAdmin):
    """
    Admin configuration for Jira Projects.
    """

    list_display = ("jira_project_key", "title", "owner", "created_at")
    search_fields = ("title", "jira_project_key")
