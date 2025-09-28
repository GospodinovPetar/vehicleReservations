from django.template import TemplateDoesNotExist

from emails.helpers.detect_changes import detect_changes
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_reservation_edited_email(before, after):
    group = after.group
    recipients = recipients_for_group(group)
    changes = detect_changes(before, after)
    ctx = {
        "group": group,
        "reservation": after,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "changes": changes,
        "total_price": getattr(after, "total_price", None),
    }
    subject = f"Reservation updated: {ctx['reference']}"
    try:
        text_body, html_body = render_pair("reservation_edited", ctx)
    except TemplateDoesNotExist:
        if changes:
            summary = "; ".join(f"{c.label}: {c.before} → {c.after}" for c in changes)
        else:
            summary = "Reservation details were updated."
        text_body, html_body = (f"{subject}\n\n{summary}", None)
    send(subject, recipients, text_body, html_body)