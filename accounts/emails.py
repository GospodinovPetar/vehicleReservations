from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.template.exceptions import TemplateDoesNotExist


def _render(base_path: str, context: dict):
    txt_path = f"{base_path}.txt"
    html_path = f"{base_path}.html"
    text_body = render_to_string(txt_path, context)
    try:
        html_body = render_to_string(html_path, context)
    except TemplateDoesNotExist:
        html_body = None
    return text_body, html_body


def send_verification_email(to_email: str, code: str, ttl_minutes: int):
    subject = "Your verification code"
    ctx = {"code": code, "ttl_minutes": ttl_minutes, "site_name": getattr(settings, "SITE_NAME", "Our Service")}
    text, html = _render("emails/verify_email/verify_email", ctx)
    send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [to_email], html_message=html)


def send_reset_password_email(to_email: str, code: str, ttl_minutes: int):
    subject = "Your password reset code"
    ctx = {"code": code, "ttl_minutes": ttl_minutes, "site_name": getattr(settings, "SITE_NAME", "Our Service")}
    text, html = _render("emails/reset_password/reset_password", ctx)
    send_mail(subject, text, settings.DEFAULT_FROM_EMAIL, [to_email], html_message=html)
