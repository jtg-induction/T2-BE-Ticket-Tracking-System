from celery import shared_task

from notifications.notifications import TicketNotification


@shared_task
def run_status_notification(ticket_id):
    TicketNotification.send_status_change(ticket_id)


@shared_task
def run_assignee_notification(ticket_id):
    TicketNotification.send_assignee_notification(ticket_id)


@shared_task
def run_deadline_notification(ticket_id):
    TicketNotification.send_deadline_reminder(ticket_id)
