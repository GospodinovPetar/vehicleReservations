from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from inventory.models.reservation import ReservationGroup, ReservationStatus
from mockpay.models import PaymentIntent, PaymentIntentStatus


class TransitionError(ValidationError):
    """Raised when a reservation group status change violates domain rules."""


@dataclass(frozen=True)
class Transition:
    """A single allowed transition rule.

    Attributes:
        to_status: Target status after the transition.
        allowed_from: Iterable of statuses from which this transition is allowed.
        require_staff: Whether only staff may perform this action.
        cancel_payment_intents: Whether to cancel in-flight payment intents first.
        require_owner_or_staff: Whether the actor must be the owner or staff.
    """
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
    Cancel any open PaymentIntents tied to the given group (idempotent).

    Open intents are those in REQUIRES_CONFIRMATION or PROCESSING. The function
    locks matching rows, updates their status to CANCELED, and returns the count.

    Args:
        group: ReservationGroup whose payment intents should be canceled.

    Returns:
        int: Number of intents updated.
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
    Perform a named transition on a ReservationGroup with full validation.

    Steps:
        - Validate `action` against TRANSITIONS.
        - Lock the group row (SELECT FOR UPDATE) and load its owner.
        - Enforce staff/owner permissions per rule.
        - Ensure current status is in the rule's `allowed_from`.
        - Optionally cancel in-flight PaymentIntents.
        - Persist the new status.

    Args:
        group_id: Primary key of the ReservationGroup to transition.
        action: Transition key (e.g., "approve", "reject", "cancel", "complete").
        actor: The user performing the action; used for permission checks.
        reason: Optional free-form reason (not persisted here, reserved for future use).

    Returns:
        ReservationGroup: The updated group instance.

    Raises:
        TransitionError: If the action is unknown or status change is not allowed.
        PermissionDenied: If the actor lacks required permissions.
        ReservationGroup.DoesNotExist: If the group_id is invalid.
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
