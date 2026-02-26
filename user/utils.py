import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import jwt
from Crypto.Cipher import AES
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



def get_aes_key():
    raw_key = settings.SECRET_KEY.encode()
    return hashlib.sha256(raw_key).digest()

def encrypt_token(raw_token):
    if not raw_token:
        return None
    
    key = get_aes_key()
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(raw_token.encode())
    
    package = {
        'nonce': base64.b64encode(cipher.nonce).decode(),
        'tag': base64.b64encode(tag).decode(),
        'ciphertext': base64.b64encode(ciphertext).decode()
    }
    return base64.b64encode(json.dumps(package).encode()).decode()

def decrypt_token(encrypted_token):
    if not encrypted_token:
        return None
    
    try:
        key = get_aes_key()
        raw_data = base64.b64decode(encrypted_token).decode()
        package = json.loads(raw_data)
        
        nonce = base64.b64decode(package['nonce'])
        tag = base64.b64decode(package['tag'])
        ciphertext = base64.b64decode(package['ciphertext'])
        
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()
    except Exception:
        return None
