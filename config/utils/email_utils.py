import sys
from django.conf import settings
from django.core.mail import EmailMessage
from django.template import Context
from django.template.loader import render_to_string


def send_email_ctrl(subject, dict, template, to_email, from_email=settings.DEFAULT_FROM_EMAIL):
    if isinstance(to_email, str):
        to_email = [to_email]

    if not dict:
        dict = {}

    try:
        html_template = template
        context = Context(dict)
        content = render_to_string(html_template, {'context': context})
        send_email = EmailMessage(subject, content, from_email, to_email)
        send_email.content_subtype = 'html'
        send_email.send()
    except Exception:
        print('erro send_email_ctrl', sys.exc_info()[0])
        raise
