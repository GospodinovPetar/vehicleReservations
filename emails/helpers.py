from dataclasses import dataclass
from typing import Any, Iterable, Sequence, Optional

from django.core.mail import send_mail
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

from config import settings


@dataclass(frozen=True)
class FieldChange:
    """A single field difference between two reservation snapshots."""
    name: str
    label: str
    before: str
    after: str


def format_value(v: Any) -> str:
    """
    Render a value as a user-friendly string.

    - Datetime-like values are localized (if tz-aware) and formatted as YYYY-MM-DD.
    - All other values are coerced with ``str()``.

    Args:
        v: Arbitrary value, often a datetime/date or model instance.

    Returns:
        str: Human-readable representation.
    """
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
    """
    Convert a reservation status (enum/str/None) to a display label.

    - If value matches ``ReservationStatus`` enum, returns its human label.
    - Falls back to empty string for ``None`` or ``str(value)`` otherwise.

    Args:
        value: Status-like value.

    Returns:
        str: Display label for the status.
    """
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
    """
    Compute a list of field changes between two reservation-like objects.

    Tracked fields:
        - start_date
        - end_date
        - pickup_location
        - return_location
        - vehicle

    Args:
        before: Pre-change reservation snapshot (object with tracked attrs).
        after: Post-change reservation snapshot (object with tracked attrs).

    Returns:
        list[FieldChange]: Ordered collection of differences.
    """
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
    """
    Return reservations for a group with common relations preloaded.

    Args:
        group: Object exposing ``.reservations`` related manager.

    Returns:
        Iterable: Queryset/iterable of reservations.
    """
    return group.reservations.select_related(
        "vehicle", "pickup_location", "return_location", "user"
    ).all()


def recipients_for_group(group) -> list[str]:
    """
    Produce a simple recipient list for a reservation group.

    Currently returns the group's user's email if present.

    Args:
        group: Object with optional ``.user.email``.

    Returns:
        list[str]: Zero-or-one email addresses.
    """
    user = getattr(group, "user", None)
    email = getattr(user, "email", None) if user else None
    return [email] if email else []


def render_pair(base_name: str, context: dict) -> tuple[str, Optional[str]]:
    """
    Render a text/HTML email pair for the given base template name.

    Looks for:
        - ``emails/{base}/{base}.txt`` (required)
        - ``emails/{base}/{base}.html`` (optional)

    Args:
        base_name: Template base name (e.g., ``"reservation_created"``).
        context: Template context.

    Returns:
        tuple[text_body, html_body_or_None]
    """
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
    """
    Send an email with text (and optional HTML) to a list of recipients.

    Args:
        subject: Email subject line.
        recipients: Sequence of recipient email addresses.
        text_body: Plaintext body (required).
        html_body: HTML body or ``None`` to omit.

    Returns:
        None. Uses Django's ``send_mail``; fails silently if configured so.
    """
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
