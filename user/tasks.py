import socket
from smtplib import SMTPException

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(
    autoretry_for=(SMTPException, socket.timeout, OSError, ConnectionError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_registration_email_task(email, signup_url):
    """
    Background task to send registration emails.
    """
    subject = "Complete Your Registration"
    message = (
        f"Hi there,\n\n"
        f"Thank you for signing up! Please click the link below to complete your registration. "
        f"This link will expire in 30 minutes:\n\n"
        f"{signup_url}\n\n"
        f"If you didn't request this, please ignore this email."
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
