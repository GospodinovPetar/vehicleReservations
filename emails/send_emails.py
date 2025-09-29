from typing import Any, List, Dict, Optional

from django.template import TemplateDoesNotExist

from emails.helpers import recipients_for_group, render_pair, send, group_items, _display_status, detect_changes


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
        "status": new_status_display,  # provide a generic 'status' for templates expecting it
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

