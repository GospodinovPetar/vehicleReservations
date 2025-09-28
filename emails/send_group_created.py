from django.template import TemplateDoesNotExist

from emails.helpers.group_items import group_items
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_group_created_email(group):
    recipients = recipients_for_group(group)
    ctx = {
        "group": group,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "items": list(group_items(group)),
    }
    subject = f"Reservation created: {ctx['reference']}"
    try:
        text_body, html_body = render_pair("reservation_created", ctx)
    except TemplateDoesNotExist:
        text_body, html_body = (
            f"Your reservation {ctx['reference']} has been created.",
            None,
        )
    send(subject, recipients, text_body, html_body)