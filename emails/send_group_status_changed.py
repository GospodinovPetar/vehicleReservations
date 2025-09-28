from django.template import TemplateDoesNotExist

from emails.helpers.group_items import group_items
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_group_status_changed_email(group, old_status, new_status):
    recipients = recipients_for_group(group)

    def _display(value):
        try:
            from inventory.models.reservation import ReservationStatus

            return ReservationStatus(value).label if value is not None else ""
        except Exception:
            return str(value or "")

    ctx = {
        "group": group,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "old_status": _display(old_status),
        "new_status": _display(new_status),
        "items": list(group_items(group)),
    }

    new_upper = (str(new_status) or "").upper()
    if new_upper == "RESERVED":
        base = "reservation_confirmed"
        subject = f"Reservation confirmed: {ctx['reference']}"
    elif new_upper == "REJECTED":
        base = "reservation_rejected"
        subject = f"Reservation rejected: {ctx['reference']}"
    else:
        base = "reservation_status_changed"
        subject = f"Reservation updated: {ctx['reference']}"

    try:
        text_body, html_body = render_pair(base, ctx)
    except TemplateDoesNotExist:
        try:
            text_body, html_body = render_pair("reservation_status_changed", ctx)
        except TemplateDoesNotExist:
            text_body = (
                f"Reservation updated: {ctx['reference']}\n"
                f"Old status: {ctx['old_status']}\n"
                f"New status: {ctx['new_status']}\n"
            )
            html_body = None
    send(subject, recipients, text_body, html_body)