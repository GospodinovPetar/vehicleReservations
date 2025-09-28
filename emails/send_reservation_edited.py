from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.template import TemplateDoesNotExist

from emails.helpers.detect_changes import detect_changes
from emails.helpers.recipients_for_group import recipients_for_group
from emails.helpers.render_pair import render_pair
from emails.helpers.send import send


def send_reservation_edited_email(before: Any, after: Any) -> None:
    group_obj: Any = after.group
    recipients_list: List[str] = recipients_for_group(group_obj)

    changes_list = detect_changes(before, after)

    reference_value: str = getattr(group_obj, "reference", None)
    if not reference_value:
        reference_value = f"#{group_obj.pk}"

    status_display_value: str = group_obj.get_status_display()

    total_price_value = getattr(after, "total_price", None)

    context: Dict[str, Any] = {
        "group": group_obj,
        "reservation": after,
        "reference": reference_value,
        "status": status_display_value,
        "changes": changes_list,
        "total_price": total_price_value,
    }

    subject_value: str = f"Reservation updated: {reference_value}"

    try:
        text_body_value, html_body_value = render_pair("reservation_edited", context)
    except TemplateDoesNotExist:
        if changes_list:
            parts: List[str] = []
            for c in changes_list:
                label_value = getattr(c, "label", "")
                before_value = getattr(c, "before", "")
                after_value = getattr(c, "after", "")
                parts.append(f"{label_value}: {before_value} → {after_value}")
            summary_value = "; ".join(parts)
        else:
            summary_value = "Reservation details were updated."
        text_body_value = f"{subject_value}\n\n{summary_value}"
        html_body_value = None

    send(subject_value, recipients_list, text_body_value, html_body_value)
