from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.core.mail import send_mail


def generate_signup_jwt(email):
    """
    Handles the creation for signup jwt

    Args:
        email: Email string to generate corresponding payload

    Returns:
        payload: Encoded jwt payload
    """

    payload = {
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        "iat": datetime.now(timezone.utc),
        "purpose": "registration",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def verify_signup_jwt(token):
    """
    Handles the verification for signup jwt

    Args:
        token: The token to be verified.

    Returns:
        email: if the token is verified it returns the email
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != "registration":
            raise ValueError("Invalid token purpose.")
        return payload["email"]
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token.")


def send_registration_email(email, signup_url):
    """
    Handles the construction and sending of the registration email.

    Args:
        email: where to send email
        signup_url: Token embadded url for registration
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


def set_auth_cookie(response, refresh_token):
    """
    Utility to set the JWT refresh token cookie.
    Args:
        response (HttpResponse): The Django response object to attach the cookie to.
        refresh_token (str): The raw refresh token string.

    Returns:
        None: Modifies the response object in-place.
    """
    response.set_cookie(
        key=settings.SIMPLE_JWT["AUTH_COOKIE"],
        value=refresh_token,
        max_age=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds(),
        secure=settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", False),
        httponly=settings.SIMPLE_JWT.get("AUTH_COOKIE_HTTP_ONLY", True),
        samesite=settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
        path=settings.SIMPLE_JWT.get("AUTH_COOKIE_PATH", "/api/"),
    )


def clear_auth_cookie(response):
    """
    Utility to remove the JWT auth cookie from a given response.

    Args:
        response (HttpResponse): The Django response object to clear the cookie from.

    Returns:
        HttpResponse: The modified response object with the deletion instruction.
    """
    cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE", "refresh_token")

    response.delete_cookie(
        key=cookie_name,
        path=settings.SIMPLE_JWT.get("AUTH_COOKIE_PATH", "/api/"),
        domain=settings.SIMPLE_JWT.get("AUTH_COOKIE_DOMAIN", None),
        samesite=settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax"),
    )
    return response
