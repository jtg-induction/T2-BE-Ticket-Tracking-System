from django.contrib import admin

from .models import Notifications


@admin.register(Notifications)
class NotificationsAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket_name", "subscriber_email", "created_at")

    list_filter = ("created_at", "ticket__project", "subscriber")

    search_fields = (
        "ticket__name",
        "subscriber__email",
        "subscriber__first_name",
        "subscriber__last_name",
    )

    list_select_related = ("ticket", "subscriber")

    def ticket_name(self, obj):
        return obj.ticket.name

    ticket_name.short_description = "Ticket"

    def subscriber_email(self, obj):
        return obj.subscriber.email

    subscriber_email.short_description = "Subscriber Email"

    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
