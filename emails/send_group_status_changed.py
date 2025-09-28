from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from django.template import TemplateDoesNotExist

from emails.helpers.group_items import group_items
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def _display_status(value: Any) -> str:
    try:
        from inventory.models.reservation import ReservationStatus

        if value is None:
            return ""
        return ReservationStatus(value).label
    except Exception:
        if value is None:
            return ""
        return str(value)


def send_group_status_changed_email(
    group: Any, old_status: Any, new_status: Any
) -> None:
    recipients_list: List[str] = recipients_for_group(group)

    group_reference_value: str = getattr(group, "reference", None)
    if not group_reference_value:
        group_reference_value = f"#{group.pk}"

    old_status_display: str = _display_status(old_status)
    new_status_display: str = _display_status(new_status)

    items_list: List[Any] = list(group_items(group))

    context: Dict[str, Any] = {
        "group": group,
        "reference": group_reference_value,
        "old_status": old_status_display,
        "new_status": new_status_display,
        "items": items_list,
    }

    new_status_upper: str = (str(new_status) if new_status is not None else "").upper()
    if new_status_upper == "RESERVED":
        base_template_name: str = "reservation_confirmed"
        subject_value: str = f"Reservation confirmed: {group_reference_value}"
    elif new_status_upper == "REJECTED":
        base_template_name = "reservation_rejected"
        subject_value = f"Reservation rejected: {group_reference_value}"
    else:
        base_template_name = "reservation_status_changed"
        subject_value = f"Reservation updated: {group_reference_value}"

    try:
        text_body_value, html_body_value = render_pair(base_template_name, context)
    except TemplateDoesNotExist:
        try:
            text_body_value, html_body_value = render_pair(
                "reservation_status_changed", context
            )
        except TemplateDoesNotExist:
            text_body_value = (
                f"Reservation updated: {group_reference_value}\n"
                f"Old status: {old_status_display}\n"
                f"New status: {new_status_display}\n"
            )
            html_body_value = None

    send(subject_value, recipients_list, text_body_value, html_body_value)
