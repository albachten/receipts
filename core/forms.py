import logging
import threading

from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template import loader

from .models import User

logger = logging.getLogger(__name__)


def send_in_background(message):
    """Send an email without blocking the request.

    Sending only happens for valid accounts, so doing it inline would let
    response time reveal whether a username or email exists.
    """
    def _send():
        try:
            message.send()
        except Exception:
            logger.exception('Failed to send email to %s', message.to)

    threading.Thread(target=_send, daemon=True).start()


class UsernameOrEmailPasswordResetForm(PasswordResetForm):
    email = forms.CharField(label='Username or email', max_length=254)

    def get_users(self, identifier):
        users = User.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier),
            is_active=True,
        ).exclude(email='')
        return (u for u in users if u.has_usable_password())

    def send_mail(self, subject_template_name, email_template_name, context,
                  from_email, to_email, html_email_template_name=None):
        # Render here, in the request thread, so {% url %} keeps the script prefix.
        subject = ''.join(loader.render_to_string(subject_template_name, context).splitlines())
        body = loader.render_to_string(email_template_name, context)
        send_in_background(EmailMultiAlternatives(subject, body, from_email, [to_email]))
