from .base import *  # noqa: F401,F403
from .base import env  # noqa: F401

# Produção: mesmos defaults do base, explicitados para não herdar
# afrouxamentos do local (DEBUG, CORS aberto, email de console).
# Nenhuma variável nova exigida em relação ao base.

# https://docs.djangoproject.com/en/4.1/ref/settings/#debug

DEBUG = env.bool("DJANGO_DEBUG", default=False)

# https://pypi.org/project/django-cors-headers/

CORS_ORIGIN_ALLOW_ALL = False

# Segurança de cookies: sempre ativos em produção, independente de DEBUG.

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Email
# https://docs.djangoproject.com/en/4.1/topics/email/

EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
