from django.contrib import admin

from user.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    """
    Admin for custom user.
    """

    list_display = (
        "email",
        "first_name",
        "last_name",
        "role",
        "is_deleted",
    )

    search_fields = (
        "email",
        "first_name",
        "last_name",
    )

    ordering = ("-created_at",)

    def get_queryset(self, request):
        """
        Include deleted records in admin.
        """
        return CustomUser.all_objects.all()

    actions = ["restore_users"]

    @admin.action(description="Restore selected users")
    def restore_users(self, request, queryset):
        """
        Unset the is_deleted flag.
        """
        queryset.update(is_deleted=False)
