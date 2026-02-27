from . import base

# Re-export all settings from base so this module exposes them to Django
for _name in dir(base):
    if not _name.startswith("_"):
        globals()[_name] = getattr(base, _name)

env = base.env

# https://docs.djangoproject.com/en/dev/ref/settings/#debug

DEBUG = env("DJANGO_DEBUG", default=True)

# https://pypi.org/project/django-cors-headers/

CORS_ORIGIN_ALLOW_ALL = True

# Email
# https://docs.djangoproject.com/en/4.1/topics/email/

EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
