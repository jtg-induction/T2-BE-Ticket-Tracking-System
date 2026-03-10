import base64
import binascii
import hashlib
import json

from Crypto.Cipher import AES
from django.conf import settings


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
        "nonce": base64.b64encode(cipher.nonce).decode(),
        "tag": base64.b64encode(tag).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }
    return base64.b64encode(json.dumps(package).encode()).decode()


def decrypt_token(encrypted_token):
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
