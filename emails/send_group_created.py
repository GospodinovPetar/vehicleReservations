from __future__ import annotations

from typing import Any, Dict, List, Tuple

from django.template import TemplateDoesNotExist

from emails.helpers.group_items import group_items
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_group_created_email(group: Any) -> None:
    recipients_list: List[str] = recipients_for_group(group)

    group_reference_value: str = getattr(group, "reference", None)
    if not group_reference_value:
        group_reference_value = f"#{group.pk}"

    status_display_value: str = group.get_status_display()
    items_list: List[Any] = list(group_items(group))

    context: Dict[str, Any] = {
        "group": group,
        "reference": group_reference_value,
        "status": status_display_value,
        "items": items_list,
    }

    subject_value: str = f"Reservation created: {group_reference_value}"

    try:
        text_body_value, html_body_value = render_pair("reservation_created", context)
    except TemplateDoesNotExist:
        text_body_value = f"Your reservation {group_reference_value} has been created."
        html_body_value = None

    send(subject_value, recipients_list, text_body_value, html_body_value)
