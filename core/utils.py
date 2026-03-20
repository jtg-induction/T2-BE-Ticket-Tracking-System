import base64
import binascii
import hashlib
import json
import re

from Crypto.Cipher import AES
from django.conf import settings
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.constants import PAGE_SIZE


def get_aes_key():
    """
    Derives a 256-bit AES key from the Django SECRET_KEY.
    Returns:
        bytes: A 32-byte hash to be used as an encryption key.
    """
    raw_key = settings.ENCRYPTION_KEY.encode()
    return hashlib.sha256(raw_key).digest()


def encrypt_token(raw_token):
    """
    Encrypts a string using AES-GCM and returns a base64 encoded JSON package.
    """
    if not raw_token:
        return None

    key = get_aes_key()
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(raw_token.encode())

    package = {
        "nonce": base64.b64encode(cipher.nonce).decode(),
        "tag": base64.b64encode(tag).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }
    return base64.b64encode(json.dumps(package).encode()).decode()


def decrypt_token(encrypted_token):
    """
    Decrypts a base64 encoded AES-GCM package.
    """
    if not encrypted_token:
        return None

    try:
        key = get_aes_key()
        raw_data = base64.b64decode(encrypted_token).decode()
        package = json.loads(raw_data)

        nonce = base64.b64decode(package["nonce"])
        tag = base64.b64decode(package["tag"])
        ciphertext = base64.b64decode(package["ciphertext"])

        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode()
    except (
        KeyError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ):
        return None


class StandardizedPagination(PageNumberPagination):
    page_size = PAGE_SIZE
    page_size_query_param = "page_size"

    def get_paginated_response(self, data):
        """
        Formats the pagination metadata for standardized_response.
        """
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


def parse_jira_error(e):
    """
    Handles DRF ErrorDetail lists and extracts clean Jira error strings.
    """
    if isinstance(e, list) and len(e) > 0:
        e = e[0]

    raw_text = str(e)

    try:
        json_match = re.search(r"\{.*\}", raw_text)

        if json_match:
            json_str = json_match.group()
            json_str = json_str.replace("\\'", "'").replace('\\"', '"')

            error_data = json.loads(json_str)

            messages = []

            field_errors = error_data.get("errors", {})
            if isinstance(field_errors, dict):
                messages.extend(field_errors.values())

            general_messages = error_data.get("errorMessages", [])
            if isinstance(general_messages, list):
                messages.extend(general_messages)

            if messages:
                return " ".join(str(m) for m in messages)

    except Exception:
        pass

    clean_fallback = re.sub(r"ErrorDetail\(string='|', code='.*'\)", "", raw_text)
    return clean_fallback.strip("[]' ")
