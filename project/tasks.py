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
def send_invitation_email(recipient_email, project_title, invite_url):
    """
    Asynchronously sends a project invitation email to a recipient.


    Args:
        recipient_email (str): The email address of the invitee.
        project_title (str): The name of the project the user is being invited to.
        invite_url (str): The unique URL/token used to accept the invitation.
    """
    subject = f"You've been invited to join {project_title}"

    plain_message = (
        f"You have been invited to join '{project_title}'.\n\n"
        f"Accept the invitation here: {invite_url}"
    )

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    </head>
    <body style="margin: 0; padding: 40px 20px; background-color: #ffffff; font-family: 'Inter'; color: #111827;">
        <div style="max-width: 500px; margin: 0 auto;">
            <h1 style="font-size: 20px; font-weight: 600; margin-bottom: 16px;">
                Project Invitation
            </h1>
            
            <p style="font-size: 16px; line-height: 1.6; color: #374151; margin-bottom: 24px;">
                You’ve been invited to join <strong>{project_title}</strong>. 
                Click the button below to accept and get started.
            </p>

            <a href="{invite_url}" style="background-color: #000000; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 15px; display: inline-block;">
                Accept Invitation
            </a>

    </body>
    </html>
    """

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [recipient_email],
        html_message=html_message,
        fail_silently=False,
    )
