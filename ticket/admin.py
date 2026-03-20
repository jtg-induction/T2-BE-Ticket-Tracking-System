from django.contrib import admin

from ticket.models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    """
    Administration interface for the Ticket model.

    Provides a comprehensive dashboard for managing tickets, including
    custom status tracking, soft-delete capabilities, and organized
    metadata views via fieldsets.
    """

    list_display = (
        "jira_id",
        "name",
        "project",
        "status",
        "priority",
        "assignee",
        "deadline",
        "is_deleted",
    )

    actions = ["soft_delete", "restore_tickets"]

    list_filter = ("status", "priority", "category", "project")

    search_fields = ("jira_id", "name", "description")

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("jira_id", "name", "description", "project", "category")},
        ),
        (
            "Status & Priority",
            {"fields": ("status", "priority", "deadline", "completed_at")},
        ),
        ("People", {"fields": ("reporter", "assignee")}),
        (
            "Audit Logs",
            {
                "classes": ("collapse",),
                "fields": (
                    "status_updated_at",
                    "status_updated_from",
                    "status_updated_by",
                ),
            },
        ),
    )

    readonly_fields = ("status_updated_at", "status_updated_from", "status_updated_by")

    def get_queryset(self, request):
        """
        Ensures the admin can see deleted records.
        """
        return Ticket.all_objects.get_queryset()

    @admin.action(description="Soft delete selected tickets")
    def soft_delete(self, request, queryset):
        """
        Marks selected tickets as deleted without removing them from the database.
        """
        queryset.update(is_deleted=True)
        self.message_user(request, "Selected tickets have been marked as deleted.")

    @admin.action(description="Restore selected tickets")
    def restore_tickets(self, request, queryset):
        """
        Reverses soft-deletion for selected tickets, making them visible in the app again.
        """
        queryset.update(is_deleted=False)
        self.message_user(request, "Selected tickets have been restored.")
