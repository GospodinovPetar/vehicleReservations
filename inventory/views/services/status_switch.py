from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from inventory.models.reservation import ReservationGroup, ReservationStatus
from mockpay.models import PaymentIntent, PaymentIntentStatus


class TransitionError(ValidationError):
    """Raised when a status change is not allowed."""


@dataclass(frozen=True)
class Transition:
    to_status: str
    allowed_from: Iterable[str]
    require_staff: bool = False
    cancel_payment_intents: bool = False
    require_owner_or_staff: bool = False


TRANSITIONS = {
    "approve": Transition(
        to_status=ReservationStatus.AWAITING_PAYMENT,
        allowed_from=[ReservationStatus.PENDING],
        require_staff=True,
    ),
    "reject": Transition(
        to_status=ReservationStatus.REJECTED,
        allowed_from=[ReservationStatus.PENDING],
        require_staff=True,
        cancel_payment_intents=True,
    ),
    "cancel": Transition(
        to_status=ReservationStatus.CANCELED,
        allowed_from=[ReservationStatus.PENDING, ReservationStatus.AWAITING_PAYMENT],
        require_owner_or_staff=True,
        cancel_payment_intents=True,
    ),
    "complete": Transition(
        to_status=ReservationStatus.COMPLETED,
        allowed_from=[ReservationStatus.AWAITING_PAYMENT],
        require_staff=True,
    ),
}


def _cancel_open_payment_intents(group: ReservationGroup) -> int:
    """
    Cancel any open intents linked to this group (idempotent).
    Returns the number of affected intents.
    """
    qs = PaymentIntent.objects.select_for_update().filter(
        reservation_group=group,
        status__in=[
            PaymentIntentStatus.REQUIRES_CONFIRMATION,
            PaymentIntentStatus.PROCESSING,
        ],
    )
    updated = 0
    for intent in qs:
        intent.status = PaymentIntentStatus.CANCELED
        intent.save(update_fields=["status"])
        updated += 1
    return updated


@transaction.atomic
def transition_group(
    *,
    group_id: int,
    action: str,
    actor: AbstractBaseUser,
    reason: Optional[str] = None,
) -> ReservationGroup:
    """
    Perform a named domain transition on a ReservationGroup with all checks,
    locking, and side-effects in one place.
    """
    if action not in TRANSITIONS:
        raise TransitionError(f"Unknown transition action '{action}'.")

    rule = TRANSITIONS[action]

    group = (
        ReservationGroup.objects.select_for_update()
        .select_related("user")
        .get(pk=group_id)
    )

    if rule.require_staff and not actor.is_staff:
        raise PermissionDenied("Only staff can perform this action.")
    if rule.require_owner_or_staff and not (
        actor.is_staff or group.user_id == actor.id
    ):
        raise PermissionDenied("Only the owner or staff can perform this action.")

    if group.status not in rule.allowed_from:
        raise TransitionError(
            f"Cannot transition group {group.reference or group.pk} "
            f"from {group.status} to {rule.to_status}."
        )

    if rule.cancel_payment_intents:
        _cancel_open_payment_intents(group)

    group.status = rule.to_status
    group.save(update_fields=["status"])

    return group
