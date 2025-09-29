from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from emails.send_emails import (
    send_group_created_email,
    send_group_status_changed_email,
    send_reservation_edited_email,
    send_vehicle_added_email,
    send_vehicle_removed_email,
)
from inventory.models.reservation import (
    ReservationGroup,
    ReservationStatus,
    VehicleReservation,
)
from mockpay.models import PaymentIntent, PaymentIntentStatus

GLOBAL_WS_GROUP = "reservations.all"


def _in_atomic_block() -> bool:
    """Return True if currently inside a transaction.atomic() block."""
    return transaction.get_connection().in_atomic_block


def _on_commit_or_now(fn: callable) -> None:
    """
    Execute `fn` on transaction commit if inside an atomic block, otherwise now.

    Keeps signal bodies concise and ensures side effects run only after a
    successful commit when needed.
    """
    if _in_atomic_block():
        transaction.on_commit(fn)
    else:
        fn()


def _ws_broadcast(
    event: str,
    reservation_payload: dict[str, Any],
    groups: Optional[Sequence[str]] = None,
    actor_user_id: Optional[int] = None,
) -> None:
    """
    Broadcast a reservation-related event to Channels groups.

    Handled by ReservationConsumer.reservation_event().
    """
    target_groups: Sequence[str] = groups or (GLOBAL_WS_GROUP,)
    layer = get_channel_layer()
    if layer is None:
        return

    base_message = {
        "type": "reservation.event",
        "event": event,
        "reservation": reservation_payload,
        "actor_user_id": actor_user_id,
    }

    for group_name in target_groups:
        async_to_sync(layer.group_send)(
            group_name, {**base_message, "group": group_name}
        )


@receiver(pre_save, sender=ReservationGroup)
def _remember_old_status(
    sender: type[ReservationGroup], instance: ReservationGroup, **_: Any
) -> None:
    """
    Cache previous status on the instance for post_save comparisons.
    """
    if not instance.pk:
        instance._old_status = None
        return

    try:
        previous: ReservationGroup = sender.objects.only("status").get(pk=instance.pk)
        instance._old_status = previous.status
    except sender.DoesNotExist:
        instance._old_status = None


@receiver(post_save, sender=ReservationGroup)
def _handle_group_post_save(
    sender: type[ReservationGroup],
    instance: ReservationGroup,
    created: bool,
    **_: Any,
) -> None:
    """
    Send emails and WebSocket broadcasts on group creation or status change.
    Also updates vehicle location availability when a group completes.
    """
    old_status = getattr(instance, "_old_status", None)
    status_changed = old_status is not None and old_status != instance.status

    def perform_email_side_effects() -> None:
        if created:
            send_group_created_email(instance)
        elif status_changed:
            send_group_status_changed_email(instance, old_status, instance.status)

    _on_commit_or_now(perform_email_side_effects)

    def perform_ws_broadcast() -> None:
        payload = {
            "kind": "group",
            "group_id": instance.id,
            "status": instance.status,
            "changed_at": timezone.now().isoformat(),
        }
        if created:
            _ws_broadcast("group.created", payload)
        elif status_changed:
            _ws_broadcast("group.status_changed", payload)

    _on_commit_or_now(perform_ws_broadcast)

    if (
        (not created)
        and status_changed
        and instance.status == ReservationStatus.COMPLETED
    ):

        def update_vehicle_locations() -> None:
            items = VehicleReservation.objects.filter(group=instance).select_related(
                "vehicle", "pickup_location", "return_location"
            )
            for item in items:
                vehicle = item.vehicle
                if item.return_location_id:
                    vehicle.available_pickup_locations.set([item.return_location_id])
                if item.pickup_location_id:
                    vehicle.available_return_locations.add(item.pickup_location_id)

        _on_commit_or_now(update_vehicle_locations)


@receiver(pre_save, sender=VehicleReservation)
def _capture_reservation_snapshot(
    sender: type[VehicleReservation], instance: VehicleReservation, **_: Any
) -> None:
    """
    Cache a 'before' snapshot for change detection in post_save.
    """
    if not instance.pk:
        instance._before_snapshot = None
        return

    try:
        before: VehicleReservation = VehicleReservation.objects.select_related(
            "group", "vehicle", "pickup_location", "return_location"
        ).get(pk=instance.pk)
    except VehicleReservation.DoesNotExist:
        before = None

    instance._before_snapshot = before


@receiver(post_save, sender=VehicleReservation)
def _reservation_created_or_edited(
    sender: type[VehicleReservation],
    instance: VehicleReservation,
    created: bool,
    **_: Any,
) -> None:
    """
    On create: email and broadcast 'created'.
    On update: detect meaningful changes, email, and broadcast 'updated'.
    """

    def perform_actions_and_broadcast() -> None:
        if created:
            send_vehicle_added_email(instance)
        else:
            before = getattr(instance, "_before_snapshot", None)
            if before is not None:
                tracked_fields: tuple[str, ...] = (
                    "start_date",
                    "end_date",
                    "pickup_location_id",
                    "return_location_id",
                    "vehicle_id",
                )
                maybe_status = "status" if hasattr(instance, "status") else None
                fields_to_compare: Iterable[str] = tracked_fields + (
                    (maybe_status,) if maybe_status else tuple()
                )
                has_changed = any(
                    getattr(before, field, None) != getattr(instance, field, None)
                    for field in fields_to_compare
                )
                if has_changed:
                    send_reservation_edited_email(before, instance)

        payload = {
            "kind": "reservation",
            "id": instance.id,
            "group_id": instance.group_id,
            "vehicle_id": instance.vehicle_id,
            "start_date": (
                instance.start_date.isoformat() if instance.start_date else None
            ),
            "end_date": instance.end_date.isoformat() if instance.end_date else None,
            "status": getattr(instance, "status", None),
            "changed_at": timezone.now().isoformat(),
        }
        _ws_broadcast(
            "reservation.created" if created else "reservation.updated",
            payload,
        )

    _on_commit_or_now(perform_actions_and_broadcast)


@receiver(post_delete, sender=VehicleReservation)
def _reservation_deleted(
    sender: type[VehicleReservation], instance: VehicleReservation, **_: Any
) -> None:
    """
    Email notification and broadcast on reservation deletion.
    """

    def perform_delete_side_effects_and_broadcast() -> None:
        send_vehicle_removed_email(instance)

        payload = {
            "kind": "reservation",
            "id": instance.id,
            "group_id": instance.group_id,
            "vehicle_id": instance.vehicle_id,
            "status": getattr(instance, "status", None),
            "changed_at": timezone.now().isoformat(),
        }
        _ws_broadcast("reservation.deleted", payload)

    _on_commit_or_now(perform_delete_side_effects_and_broadcast)


@receiver(post_save, sender=VehicleReservation)
def _auto_cleanup_payment_on_pending(
    sender: type[VehicleReservation], instance: VehicleReservation, **_: Any
) -> None:
    """
    If a reservation in a group marked AWAITING_PAYMENT is modified, cancel any
    in-flight PaymentIntents and move the group back to PENDING, then broadcast.
    """
    group = instance.group
    if group is None or group.status != ReservationStatus.AWAITING_PAYMENT:
        return

    def perform_cleanup_and_broadcast() -> None:
        PaymentIntent.objects.filter(
            reservation_group=group,
            status__in=[
                PaymentIntentStatus.REQUIRES_CONFIRMATION,
                PaymentIntentStatus.PROCESSING,
            ],
        ).update(status=PaymentIntentStatus.CANCELED)

        ReservationGroup.objects.filter(pk=group.pk).update(
            status=ReservationStatus.PENDING
        )

        payload = {
            "kind": "group",
            "group_id": group.id,
            "status": ReservationStatus.PENDING,
            "changed_at": timezone.now().isoformat(),
        }
        _ws_broadcast("group.status_changed", payload)

    _on_commit_or_now(perform_cleanup_and_broadcast)
