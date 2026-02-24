from .base import *

DEBUG = False

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['domain.com'])

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SIMPLE_JWT['AUTH_COOKIE_SECURE'] = True
SIMPLE_JWT['AUTH_COOKIE_SAMESITE'] = 'Strict'

CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOWED_ORIGINS = [
    "https://frontend-domain.com",
    "https://www.frontend-domain.com",
]
