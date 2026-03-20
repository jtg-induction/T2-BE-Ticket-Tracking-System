from django.contrib import admin

from project.models import ProjectInvitation, ProjectMember, ProjectModel


@admin.register(ProjectModel)
class ProjectAdmin(admin.ModelAdmin):
    """
    Admin configuration for Jira Projects.
    """

    list_display = ("jira_project_key", "title", "owner", "created_at")
    search_fields = ("title", "jira_project_key")


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    """
    Admin interface for ProjectMember.
    """

    list_select_related = ("project", "user")
    list_display = ("project", "user", "is_admin", "created_at")
    search_fields = (
        "project__title",
        "user__email",
        "user__first_name",
        "user__last_name",
    )


@admin.register(ProjectInvitation)
class ProjectInvitationAdmin(admin.ModelAdmin):
    """
    Admin interface for ProjectInvitation.

    Tracks the lifecycle of invitations, including who sent them,
    whether they have been accepted, and when they expire.
    """

    list_select_related = ("project", "invitee", "invited_by")
    list_display = (
        "project",
        "invitee",
        "is_admin",
        "is_accepted",
        "invited_by",
        "created_at",
        "expires_at",
    )
    search_fields = (
        "project__title",
        "invitee__email",
        "invitee__first_name",
        "invitee__last_name",
    )
