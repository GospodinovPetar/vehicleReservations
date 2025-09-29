from dataclasses import dataclass
from typing import Any, Iterable, Sequence, Optional

from django.core.mail import send_mail
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

from config import settings


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


def detect_changes(before, after) -> list[FieldChange]:
    tracked = [
        ("start_date", "Start date"),
        ("end_date", "End date"),
        ("pickup_location", "Pickup location"),
        ("return_location", "Return location"),
        ("vehicle", "Vehicle"),
    ]
    changes: list[FieldChange] = []
    for attr, label in tracked:
        b = getattr(before, attr, None)
        a = getattr(after, attr, None)
        if b != a:
            changes.append(
                FieldChange(
                    name=attr,
                    label=label,
                    before=format_value(b),
                    after=format_value(a),
                )
            )
    return changes


def group_items(group) -> Iterable:
    return group.reservations.select_related(
        "vehicle", "pickup_location", "return_location", "user"
    ).all()


def recipients_for_group(group) -> list[str]:
    user = getattr(group, "user", None)
    email = getattr(user, "email", None) if user else None
    return [email] if email else []


def render_pair(base_name: str, context: dict) -> tuple[str, Optional[str]]:
    txt_path = f"emails/{base_name}/{base_name}.txt"
    html_path = f"emails/{base_name}/{base_name}.html"
    text_body = render_to_string(txt_path, context)
    try:
        html_body = render_to_string(html_path, context)
    except TemplateDoesNotExist:
        html_body = None
    return text_body, html_body


def send(
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
