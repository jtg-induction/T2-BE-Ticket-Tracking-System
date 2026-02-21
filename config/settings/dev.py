from .base import *

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

SIMPLE_JWT['AUTH_COOKIE_SECURE'] = False

CORS_ALLOW_ALL_ORIGINS = True 

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
