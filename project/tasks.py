from smtplib import SMTPException

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(
    autoretry_for=(SMTPException,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_invitation_email(recipient_email, project_title, invite_url):
    subject = f"You've been invited to join {project_title}"
    message = f"You have been invited to collaborate on the project '{project_title}'. Click the link below to accept:\n\n{invite_url}"

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [recipient_email],
        fail_silently=False,
    )
