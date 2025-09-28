from django.template import TemplateDoesNotExist

from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_vehicle_added_email(reservation):
    group = reservation.group
    if not group:
        return
    had_items_before = group.reservations.exclude(pk=reservation.pk).exists()
    if not had_items_before:
        return

    recipients = recipients_for_group(group)
    ctx = {
        "group": group,
        "reservation": reservation,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
    }
    subject = f"Vehicle added: {reservation.vehicle}"
    try:
        text_body, html_body = render_pair("vehicle_added", ctx)
    except TemplateDoesNotExist:
        text_body, html_body = (
            f"A vehicle was added to reservation {ctx['reference']}: {reservation.vehicle}.",
            None,
        )
    send(subject, recipients, text_body, html_body)