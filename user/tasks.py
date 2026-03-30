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
    Background task to send registration emails with both plain text and HTML templates.

    Args:
        email (str): The recipient's email address.
        signup_url (str): The unique URL used to complete registration.
    """
    subject = "Complete Your Registration"

    plain_message = (
        f"Hi there,\n\n"
        f"Thank you for signing up! Please click the link below to complete your registration. "
        f"This link will expire in 30 minutes:\n\n"
        f"{signup_url}\n\n"
        f"If you didn't request this, please ignore this email."
    )

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    </head>
    <body style="margin: 0; padding: 40px 20px; background-color: #ffffff; font-family: 'Inter', sans-serif; color: #111827;">
        <div style="max-width: 500px; margin: 0 auto;">
            <h1 style="font-size: 20px; font-weight: 600; margin-bottom: 16px; color: #111827;">
                Complete Your Registration
            </h1>
            
            <p style="font-size: 16px; line-height: 1.6; color: #374151; margin-bottom: 12px;">
                Hi there,
            </p>

            <p style="font-size: 16px; line-height: 1.6; color: #374151; margin-bottom: 24px;">
                Thank you for signing up! Click the button below to complete your registration. 
                Please note that <strong>this link will expire in 30 minutes</strong>.
            </p>

            <a href="{signup_url}" style="background-color: #000000; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 15px; display: inline-block;">
                Verify Email Address
            </a>

            <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 32px 0;">

            <p style="font-size: 13px; color: #6b7280; line-height: 1.5;">
                If you did not create an account, no further action is required.
            </p>
        </div>
    </body>
    </html>
    """

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        html_message=html_message,
        fail_silently=False,
    )
