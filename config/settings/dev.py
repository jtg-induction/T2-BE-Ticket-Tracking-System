from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

SIMPLE_JWT["AUTH_COOKIE_SECURE"] = False

CORS_ALLOW_ALL_ORIGINS = True

DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
