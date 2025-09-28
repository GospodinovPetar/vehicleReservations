from typing import Optional, Sequence

from django.core.mail import send_mail

from config import settings


def send(
    subject: str, recipients: Sequence[str], text_body: str, html_body: Optional[str]
):
    if not recipients:
        return
    send_mail(
        subject=subject,
        message=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        recipient_list=list(recipients),
        html_message=html_body,
        fail_silently=True,
    )
