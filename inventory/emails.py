from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _send_email(subject: str, template_base: str, context: dict, to_email: str):
    """
    Renders emails/emails/<template_base>.{txt,html} and sends both text+html.
    """
    text_body = render_to_string(f"emails/{template_base}.txt", context)
    html_body = render_to_string(f"emails/{template_base}.html", context)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


def send_reservation_created_email(reservation):
    ctx = {"reservation": reservation, "user": reservation.user}
    subject = f"Reservation received — #{reservation.pk}"
    _send_email(subject, "reservation_created", ctx, reservation.user.email)


def send_reservation_status_changed_email(reservation, old_status, new_status):
    # Choose a template based on the new status.
    status = reservation.status
    template_map = {
        getattr(status, "RESERVED", "RESERVED"): "reservation_confirmed",
        getattr(status, "REJECTED", "REJECTED"): "reservation_rejected",
    }
    template = template_map.get(new_status, "reservation_status_changed")

    ctx = {
        "reservation": reservation,
        "user": reservation.user,
        "old_status": old_status,
        "new_status": new_status,
    }
    subject = (
        f"Reservation #{reservation.pk} {reservation.get_status_display().lower()}"
    )
    _send_email(subject, template, ctx, reservation.user.email)
