from typing import Iterable, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.template.exceptions import TemplateDoesNotExist


def _recipients_for_group(group) -> list[str]:
    user = getattr(group, "user", None)
    email = getattr(user, "email", None) if user else None
    return [email] if email else []


def _group_items(group) -> Iterable:
    return group.reservations.select_related(
        "vehicle", "pickup_location", "return_location", "user"
    ).all()


def _render_pair(base_name: str, context: dict) -> tuple[str, Optional[str]]:
    """
    Render txt/html pair using your existing folder convention:
      emails/<base>/<base>.txt and emails/<base>/<base>.html

    Returns (text_body, html_body), where html_body can be None if missing.
    """
    txt_path = f"emails/{base_name}/{base_name}.txt"
    html_path = f"emails/{base_name}/{base_name}.html"

    text_body = render_to_string(txt_path, context)
    try:
        html_body = render_to_string(html_path, context)
    except TemplateDoesNotExist:
        html_body = None
    return text_body, html_body


def _send(subject: str, recipients: list[str], text_body: str, html_body: Optional[str]):
    if not recipients:
        return
    send_mail(
        subject=subject,
        message=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        recipient_list=recipients,
        html_message=html_body,
        fail_silently=True,
    )


def send_group_created_email(group) -> None:
    """
    ONE email per group when created. Uses 'reservation_created' templates.
    """
    recipients = _recipients_for_group(group)
    ctx = {
        "group": group,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "items": list(_group_items(group)),
    }
    subject = f"Reservation created: {ctx['reference']}"

    try:
        text_body, html_body = _render_pair("reservation_created", ctx)
    except TemplateDoesNotExist:
        lines = [
            f"Reservation created: {ctx['reference']}",
            f"Status: {ctx['status']}",
            "",
            "Items:",
        ]
        for r in ctx["items"]:
            lines.append(
                f"- {r.vehicle} | {r.start_date:%Y-%m-%d} → {r.end_date:%Y-%m-%d} | "
                f"{r.pickup_location} → {r.return_location}"
            )
        text_body, html_body = "\n".join(lines), None

    _send(subject, recipients, text_body, html_body)


# ---------- GROUP: STATUS CHANGED ----------

def send_group_status_changed_email(group, old_status, new_status) -> None:
    """
    Group-scoped status change. We pick the most specific template name:
      - RESERVED  -> 'reservation_confirmed'
      - REJECTED  -> 'reservation_rejected'
      - otherwise -> 'reservation_status_changed'
    """
    recipients = _recipients_for_group(group)

    get_disp = getattr(group, "get_status_display", lambda: str(new_status))
    new_disp = get_disp()
    old_disp = getattr(group, "get_status_display", lambda: str(old_status))()

    ctx = {
        "group": group,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "old_status": old_disp,
        "new_status": new_disp,
        "items": list(_group_items(group)),
    }

    status_name = str(new_status)
    status_name_upper = status_name.upper()
    if status_name_upper == "RESERVED":
        base = "reservation_confirmed"
        subject = f"Reservation confirmed: {ctx['reference']}"
    elif status_name_upper == "REJECTED":
        base = "reservation_rejected"
        subject = f"Reservation rejected: {ctx['reference']}"
    else:
        base = "reservation_status_changed"
        subject = f"Reservation updated: {ctx['reference']}"

    try:
        text_body, html_body = _render_pair(base, ctx)
    except TemplateDoesNotExist:
        try:
            text_body, html_body = _render_pair("reservation_status_changed", ctx)
        except TemplateDoesNotExist:
            text_body = (
                f"Reservation updated: {ctx['reference']}\n"
                f"Old status: {ctx['old_status']}\n"
                f"New status: {ctx['new_status']}\n"
            )
            html_body = None

    _send(subject, recipients, text_body, html_body)



def send_reservation_edited_email(group, reservation, changes: list[dict]) -> None:
    """
    Use in your 'edit_reservation' view after saving changes.
    Expects `changes` as [{'label': 'Vehicle', 'before': 'A', 'after': 'B'}, ...]
    Uses 'reservation_edited' templates.
    """
    recipients = _recipients_for_group(group)
    ctx = {
        "group": group,
        "reservation": reservation,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "changes": changes,
        "items": list(_group_items(group)),
        "total_price": getattr(reservation, "total_price", None),
    }
    subject = f"Reservation updated: {ctx['reference']}"

    try:
        text_body, html_body = _render_pair("reservation_edited", ctx)
    except TemplateDoesNotExist:
        # Simple fallback summarizing changes
        lines = [
            f"Reservation updated: {ctx['reference']}",
            f"Status: {ctx['status']}",
            "",
            "Changes:",
        ]
        for c in changes or []:
            lines.append(f"- {c.get('label')}: {c.get('before')} → {c.get('after')}")
        text_body, html_body = "\n".join(lines), None

    _send(subject, recipients, text_body, html_body)


def send_vehicle_added_email(group, reservation) -> None:
    """
    Call in your 'add_vehicle' view after creating the VehicleReservation.
    Uses 'vehicle_added' templates.
    """
    recipients = _recipients_for_group(group)
    ctx = {
        "group": group,
        "reservation": reservation,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "items": list(_group_items(group)),
    }
    subject = f"Vehicle added to reservation: {ctx['reference']}"

    try:
        text_body, html_body = _render_pair("vehicle_added", ctx)
    except TemplateDoesNotExist:
        text_body, html_body = (
            f"Vehicle added to reservation {ctx['reference']}: {reservation.vehicle}",
            None,
        )

    _send(subject, recipients, text_body, html_body)


def send_vehicle_removed_email(group, reservation) -> None:
    """
    Call in your 'delete_reservation' (remove vehicle) flow BEFORE deleting the row,
    or pass a lightweight object containing needed fields after deletion.
    Uses 'vehicle_removed' templates.
    """
    recipients = _recipients_for_group(group)
    ctx = {
        "group": group,
        "reservation": reservation,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "items": list(_group_items(group)),
    }
    subject = f"Vehicle removed from reservation: {ctx['reference']}"

    try:
        text_body, html_body = _render_pair("vehicle_removed", ctx)
    except TemplateDoesNotExist:
        text_body, html_body = (
            f"Vehicle removed from reservation {ctx['reference']}: {reservation.vehicle}",
            None,
        )

    _send(subject, recipients, text_body, html_body)
