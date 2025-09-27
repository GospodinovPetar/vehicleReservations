from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from django.conf import settings
from django.core.mail import send_mail
from django.template.exceptions import TemplateDoesNotExist
from django.template.loader import render_to_string


def _recipients_for_group(group) -> list[str]:
    user = getattr(group, "user", None)
    email = getattr(user, "email", None) if user else None
    return [email] if email else []


def _group_items(group) -> Iterable:
    return group.reservations.select_related(
        "vehicle", "pickup_location", "return_location", "user"
    ).all()


def _render_pair(base_name: str, context: dict) -> tuple[str, Optional[str]]:
    txt_path = f"emails/{base_name}/{base_name}.txt"
    html_path = f"emails/{base_name}/{base_name}.html"
    text_body = render_to_string(txt_path, context)
    try:
        html_body = render_to_string(html_path, context)
    except TemplateDoesNotExist:
        html_body = None
    return text_body, html_body


def _send(
    subject: str, recipients: Sequence[str], text_body: str, html_body: Optional[str]
):
    if not recipients:
        return
    send_mail(
        subject=subject,
        message=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        recipient_list=list(recipients),
        html_message=html_body,
        fail_silently=True,
    )


def send_group_created_email(group):
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
        text_body, html_body = (
            f"Your reservation {ctx['reference']} has been created.",
            None,
        )
    _send(subject, recipients, text_body, html_body)


def send_group_status_changed_email(group, old_status, new_status):
    recipients = _recipients_for_group(group)

    def _display(value):
        try:
            from inventory.models.reservation import ReservationStatus

            return ReservationStatus(value).label if value is not None else ""
        except Exception:
            return str(value or "")

    ctx = {
        "group": group,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "old_status": _display(old_status),
        "new_status": _display(new_status),
        "items": list(_group_items(group)),
    }

    new_upper = (str(new_status) or "").upper()
    if new_upper == "RESERVED":
        base = "reservation_confirmed"
        subject = f"Reservation confirmed: {ctx['reference']}"
    elif new_upper == "REJECTED":
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


def send_vehicle_added_email(reservation):
    group = reservation.group
    if not group:
        return
    had_items_before = group.reservations.exclude(pk=reservation.pk).exists()
    if not had_items_before:
        return

    recipients = _recipients_for_group(group)
    ctx = {
        "group": group,
        "reservation": reservation,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
    }
    subject = f"Vehicle added: {reservation.vehicle}"
    try:
        text_body, html_body = _render_pair("vehicle_added", ctx)
    except TemplateDoesNotExist:
        text_body, html_body = (
            f"A vehicle was added to reservation {ctx['reference']}: {reservation.vehicle}.",
            None,
        )
    _send(subject, recipients, text_body, html_body)


def send_vehicle_removed_email(reservation_snapshot):
    group = reservation_snapshot.group
    recipients = _recipients_for_group(group)
    ctx = {
        "group": group,
        "reservation": reservation_snapshot,
        "reference": getattr(group, "reference", None) or f"#{group.pk}",
        "status": group.get_status_display(),
        "items": list(_group_items(group)),
    }
    subject = f"Vehicle removed from reservation: {ctx['reference']}"
    try:
        text_body, html_body = _render_pair("vehicle_removed", ctx)
    except TemplateDoesNotExist:
        text_body, html_body = (
            f"Vehicle removed from reservation {ctx['reference']}: {reservation_snapshot.vehicle}.",
            None,
        )
    _send(subject, recipients, text_body, html_body)


@dataclass(frozen=True)
class _FieldChange:
    name: str
    label: str
    before: str
    after: str


def _format_value(v):
    from django.utils import timezone

    if hasattr(v, "strftime"):
        if hasattr(v, "tzinfo") and v.tzinfo:
            v = timezone.localtime(v)
        return v.strftime("%Y-%m-%d")
    return str(v)


def _detect_changes(before, after) -> list[_FieldChange]:
    tracked = [
        ("start_date", "Start date"),
        ("end_date", "End date"),
        ("pickup_location", "Pickup location"),
        ("return_location", "Return location"),
        ("vehicle", "Vehicle"),
    ]
    changes: list[_FieldChange] = []
    for attr, label in tracked:
        b = getattr(before, attr, None)
        a = getattr(after, attr, None)
        if b != a:
            changes.append(
                _FieldChange(
                    name=attr,
                    label=label,
                    before=_format_value(b),
                    after=_format_value(a),
                )
            )
    return changes


def send_reservation_edited_email(before, after):
    group = after.group
    recipients = _recipients_for_group(group)
    changes = _detect_changes(before, after)
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
        text_body, html_body = _render_pair("reservation_edited", ctx)
    except TemplateDoesNotExist:
        if changes:
            summary = "; ".join(f"{c.label}: {c.before} → {c.after}" for c in changes)
        else:
            summary = "Reservation details were updated."
        text_body, html_body = (f"{subject}\n\n{summary}", None)
    _send(subject, recipients, text_body, html_body)
