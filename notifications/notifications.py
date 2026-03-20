from datetime import timedelta

from django.core.mail import send_mail
from django.utils import timezone

from notifications.models import Notifications
from ticket.models import Ticket


class TicketNotification:
    @staticmethod
    def send_status_change(ticket_id):
        ticket = Ticket.objects.get(pk=ticket_id)
        subscribers = Notifications.objects.filter(ticket=ticket).values_list(
            "subscriber__email", flat=True
        )

        send_mail(
            subject=f"Status Updated: {ticket.name}",
            message=f"Ticket {ticket.name} in {ticket.project.name} is now {ticket.status}.",
            from_email="noreply@company.com",
            recipient_list=list(subscribers),
        )

    @staticmethod
    def send_assignee_notification(ticket_id):
        ticket = Ticket.objects.get(pk=ticket_id)
        if ticket.assignee:
            send_mail(
                subject="New Assignment",
                message=f"You have been assigned to: {ticket.name}",
                from_email="noreply@company.com",
                recipient_list=[ticket.assignee.email],
            )

    @staticmethod
    def send_deadline_reminder(ticket_id):
        ticket = Ticket.objects.get(pk=ticket_id)
        subscribers = Notifications.objects.filter(ticket=ticket).values_list(
            "subscriber__email", flat=True
        )

        send_mail(
            subject=f"Deadline Approaching: {ticket.name}",
            message=f"Reminder: The deadline for {ticket.name} is {ticket.deadline}.",
            from_email="notifications@company.com",
            recipient_list=list(subscribers),
        )

        two_hour_reminder = ticket.deadline - timedelta(hours=2)

        if two_hour_reminder > timezone.now():
            from .tasks import run_deadline_notification

            new_task = run_deadline_notification.apply_async(
                args=[ticket.id], eta=two_hour_reminder
            )
            ticket.deadline_task_id = new_task.id
            ticket.save(update_fields=["deadline_task_id"])
