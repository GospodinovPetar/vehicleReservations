from dataclasses import dataclass

from django.template import TemplateDoesNotExist

from emails.helpers.group_items import group_items
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_vehicle_removed_email(reservation_snapshot):
    group = reservation_snapshot.group
    recipients = recipients_for_group(group)
    ctx = {
        "group": group,
        "reservation": reservation_snapshot,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "items": list(group_items(group)),
    }
    subject = f"Vehicle removed from reservation: {ctx['reference']}"
    try:
        text_body, html_body = render_pair("vehicle_removed", ctx)
    except TemplateDoesNotExist:
        text_body, html_body = (
            f"Vehicle removed from reservation {ctx['reference']}: {reservation_snapshot.vehicle}.",
            None,
        )
    send(subject, recipients, text_body, html_body)


@dataclass(frozen=True)
class FieldChange:
    name: str
    label: str
    before: str
    after: str


def format_value(v):
    from django.utils import timezone

    if hasattr(v, "strftime"):
        if hasattr(v, "tzinfo") and v.tzinfo:
            v = timezone.localtime(v)
        return v.strftime("%Y-%m-%d")
    return str(v)