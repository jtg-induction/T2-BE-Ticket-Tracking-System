from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.core.mail import send_mail


def generate_signup_jwt(email):
    """
    Handles the creation for signup jwt
    """
    payload = {
        'email': email,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=30),
        'iat': datetime.now(timezone.utc),
        'purpose': 'registration'
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

def verify_signup_jwt(token):
    """
    Handles the verification for signup jwt
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        if payload.get('purpose') != 'registration':
            raise ValueError("Invalid token purpose.")
        return payload['email']
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token.")

def send_registration_email(email, signup_url):
    """
    Handles the construction and sending of the registration email.
    """
    subject = "Complete Your Registration"
    message = (
        f"Hi there,\n\n"
        f"Thank you for signing up! Please click the link below to complete your registration. "
        f"This link will expire in 30 minutes:\n\n"
        f"{signup_url}\n\n"
        f"If you didn't request this, please ignore this email."
    )
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [email]

    send_mail(
        subject,
        message,
        from_email,
        recipient_list,
        fail_silently=False,
    )
