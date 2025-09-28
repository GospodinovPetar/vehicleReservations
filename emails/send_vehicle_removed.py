from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.template import TemplateDoesNotExist

from emails.helpers.group_items import group_items
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_vehicle_removed_email(reservation_snapshot: Any) -> None:
    group_obj: Any = getattr(reservation_snapshot, "group", None)
    recipients_list: List[str] = recipients_for_group(group_obj)

    reference_value: str = getattr(group_obj, "reference", None)
    if not reference_value:
        reference_value = f"#{group_obj.pk}"

    status_display_value: str = group_obj.get_status_display()

    items_list: List[Any] = list(group_items(group_obj))

    context: Dict[str, Any] = {
        "group": group_obj,
        "reservation": reservation_snapshot,
        "reference": reference_value,
        "status": status_display_value,
        "items": items_list,
    }

    subject_value: str = f"Vehicle removed from reservation: {reference_value}"

    try:
        text_body_value, html_body_value = render_pair("vehicle_removed", context)
    except TemplateDoesNotExist:
        vehicle_str: str = str(getattr(reservation_snapshot, "vehicle", ""))
        text_body_value = (
            f"Vehicle removed from reservation {reference_value}: {vehicle_str}."
        )
        html_body_value = None

    send(subject_value, recipients_list, text_body_value, html_body_value)


@dataclass(frozen=True)
class FieldChange:
    name: str
    label: str
    before: str
    after: str


def format_value(v: Any) -> str:
    from django.utils import timezone

    value = v

    if hasattr(value, "strftime"):
        has_tzinfo = hasattr(value, "tzinfo")
        if has_tzinfo and getattr(value, "tzinfo"):
            value = timezone.localtime(value)
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            return str(value)

    return str(value)
