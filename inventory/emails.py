from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from inventory.models.reservation import ReservationStatus


def _send_email(subject: str, template_base: str, context: dict, to_email: str):
    """
    Renders emails/emails/<template_base>.{txt,html} and sends both text+html.
    """
    text_body = render_to_string(f"emails/{template_base}/{template_base}.txt", context)
    html_body = render_to_string(f"emails/{template_base}/{template_base}.html", context)

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
    template_map = {
        ReservationStatus.RESERVED: "reservation_confirmed",
        ReservationStatus.REJECTED: "reservation_rejected",
        ReservationStatus.CANCELED: "reservation_status_changed",
        ReservationStatus.AWAITING_PAYMENT: "reservation_status_changed",
        ReservationStatus.PENDING: "reservation_status_changed",
        ReservationStatus.COMPLETED: "reservation_status_changed",
    }
    template = template_map.get(new_status, "reservation_status_changed")

    ctx = {
        "reservation": reservation,
        "user": reservation.user,
        "old_status": old_status,
        "new_status": new_status,
    }
    subject = f"Reservation #{getattr(reservation, 'pk', getattr(reservation, 'id', ''))} {reservation.get_status_display().lower()}"
    _send_email(subject, template, ctx, reservation.user.email)


def send_vehicle_removed_email(reservation):
    ctx = {"reservation": reservation, "user": reservation.user}
    subject = f"Vehicle removed from reservation {reservation.group.reference or '#' + str(reservation.group.pk)}"
    _send_email(subject, "vehicle_removed", ctx, reservation.user.email)


def send_vehicle_updated_email(reservation, changed_fields):
    ctx = {"reservation": reservation, "user": reservation.user, "changed_fields": changed_fields}
    subject = f"Vehicle updated in reservation {reservation.group.reference or '#' + str(reservation.group.pk)}"
    _send_email(subject, "vehicle_updated", ctx, reservation.user.email)


def send_group_status_changed_email(group, old_status, new_status):
    class _Shim:
        def __init__(self, group):
            self.group = group
            self.user = group.user
            self.status = new_status
            self.pk = group.pk
        def get_status_display(self):
            try:
                return group.get_status_display()
            except Exception:
                return str(new_status)

    shim = _Shim(group)
    send_reservation_status_changed_email(shim, old_status, new_status)

def send_vehicle_added_email(reservation):
    ctx = {"reservation": reservation, "user": reservation.user}
    subject = (
        f"Vehicle added to reservation "
        f"{(reservation.group.reference or '#' + str(reservation.group.pk)) if reservation.group else f'#{reservation.pk}'}"
    )
    _send_email(subject, "vehicle_added", ctx, reservation.user.email)