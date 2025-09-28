from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from django.template import TemplateDoesNotExist

from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_vehicle_added_email(reservation: Any) -> None:
    group_obj: Optional[Any] = getattr(reservation, "group", None)
    if group_obj is None:
        return

    other_items_exist: bool = group_obj.reservations.exclude(
        pk=getattr(reservation, "pk", None)
    ).exists()
    if not other_items_exist:
        return

    recipients_list: List[str] = recipients_for_group(group_obj)

    reference_value: str = getattr(group_obj, "reference", None)
    if not reference_value:
        reference_value = f"#{group_obj.pk}"

    status_display_value: str = group_obj.get_status_display()

    context: Dict[str, Any] = {
        "group": group_obj,
        "reservation": reservation,
        "reference": reference_value,
        "status": status_display_value,
    }

    subject_value: str = f"Vehicle added: {getattr(reservation, 'vehicle', '')}"

    try:
        text_body_value, html_body_value = render_pair("vehicle_added", context)
    except TemplateDoesNotExist:
        text_body_value = f"A vehicle was added to reservation {reference_value}: {getattr(reservation, 'vehicle', '')}."
        html_body_value = None

    send(subject_value, recipients_list, text_body_value, html_body_value)
