from __future__ import annotations

from typing import Any, List, Optional

from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils.timezone import now
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from emails.send_emails import (
    send_vehicle_added_email,
    send_reservation_edited_email,
    send_vehicle_removed_email,
    send_group_created_email,
    send_group_status_changed_email,
)
from inventory.models.reservation import (
    ReservationGroup,
    VehicleReservation,
    ReservationStatus,
)
from mockpay.models import PaymentIntent, PaymentIntentStatus



GLOBAL_WS_GROUP = "reservations.all"


def _ws_broadcast(event: str, reservation_payload: dict, groups: Optional[list[str]] = None, actor_user_id: Optional[int] = None) -> None:
    """
    Broadcast a reservation-related event to Channels groups.

    The event will be handled by ReservationConsumer.reservation_event().
    """
    groups = groups or [GLOBAL_WS_GROUP]
    layer = get_channel_layer()

    message = {
        "type": "reservation.event",
        "event": event,
        "reservation": reservation_payload,
        "actor_user_id": actor_user_id,
    }
    for g in groups:
        async_to_sync(layer.group_send)(g, {**message, "group": g})



@receiver(pre_save, sender=ReservationGroup)
def _remember_old_status(
    sender: type[ReservationGroup], instance: ReservationGroup, **kwargs: Any
) -> None:
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
    **kwargs: Any,
) -> None:
    old_status_value = getattr(instance, "_old_status", None)
    status_changed_flag = (
        old_status_value is not None and old_status_value != instance.status
    )

    def perform_email_side_effects() -> None:
        if created:
            send_group_created_email(instance)
            return
        if status_changed_flag:
            send_group_status_changed_email(instance, old_status_value, instance.status)

    connection_in_atomic_block = transaction.get_connection().in_atomic_block
    if connection_in_atomic_block:
        transaction.on_commit(perform_email_side_effects)
    else:
        perform_email_side_effects()

    # WS broadcast for group create/status changes
    def perform_ws_broadcast() -> None:
        payload = {
            "kind": "group",
            "group_id": instance.id,
            "status": instance.status,
            "changed_at": now().isoformat(),
        }
        if created:
            _ws_broadcast("group.created", payload)
        elif status_changed_flag:
            _ws_broadcast("group.status_changed", payload)

    if connection_in_atomic_block:
        transaction.on_commit(perform_ws_broadcast)
    else:
        perform_ws_broadcast()

    if (
        (not created)
        and status_changed_flag
        and instance.status == ReservationStatus.COMPLETED
    ):
        items_qs = VehicleReservation.objects.filter(group=instance).select_related(
            "vehicle", "pickup_location", "return_location"
        )
        for item in items_qs:
            vehicle_obj = item.vehicle
            if item.return_location_id:
                vehicle_obj.available_pickup_locations.set([item.return_location_id])
            if item.pickup_location_id:
                vehicle_obj.available_return_locations.add(item.pickup_location_id)



@receiver(pre_save, sender=VehicleReservation)
def _capture_reservation_snapshot(
    sender: type[VehicleReservation], instance: VehicleReservation, **kwargs: Any
) -> None:
    if not instance.pk:
        instance._before_snapshot = None
        return
    try:
        before_value: VehicleReservation = VehicleReservation.objects.select_related(
            "group", "vehicle", "pickup_location", "return_location"
        ).get(pk=instance.pk)
    except VehicleReservation.DoesNotExist:
        before_value = None
    instance._before_snapshot = before_value


@receiver(post_save, sender=VehicleReservation)
def _reservation_created_or_edited(
    sender: type[VehicleReservation],
    instance: VehicleReservation,
    created: bool,
    **kwargs: Any,
) -> None:
    def perform_actions_and_broadcast() -> None:
        # Email side-effects (existing behavior)
        if created:
            send_vehicle_added_email(instance)
        else:
            before_snapshot = getattr(instance, "_before_snapshot", None)
            if before_snapshot is not None:
                tracked_fields: List[str] = [
                    "start_date",
                    "end_date",
                    "pickup_location_id",
                    "return_location_id",
                    "vehicle_id",
                    # NOTE: if your VehicleReservation has a "status" field,
                    # add "status" here to include it in "updated" changes.
                    "status" if hasattr(instance, "status") else None,
                ]
                tracked_fields = [f for f in tracked_fields if f]
                has_changed = any(
                    getattr(before_snapshot, f, None) != getattr(instance, f, None)
                    for f in tracked_fields
                )
                if has_changed:
                    send_reservation_edited_email(before_snapshot, instance)

        # WS broadcast (new)
        payload = {
            "kind": "reservation",
            "id": instance.id,
            "group_id": instance.group_id,
            "vehicle_id": instance.vehicle_id,
            "start_date": instance.start_date.isoformat() if instance.start_date else None,
            "end_date": instance.end_date.isoformat() if instance.end_date else None,
            # include status if the model has it
            "status": getattr(instance, "status", None),
            "changed_at": now().isoformat(),
        }
        _ws_broadcast(
            "reservation.created" if created else "reservation.updated",
            payload,
        )

    connection_in_atomic_block = transaction.get_connection().in_atomic_block
    if connection_in_atomic_block:
        transaction.on_commit(perform_actions_and_broadcast)
    else:
        perform_actions_and_broadcast()


@receiver(post_delete, sender=VehicleReservation)
def _reservation_deleted(
    sender: type[VehicleReservation], instance: VehicleReservation, **kwargs: Any
) -> None:
    def perform_delete_side_effects_and_broadcast() -> None:
        # email (existing)
        send_vehicle_removed_email(instance)
        # WS broadcast (new)
        payload = {
            "kind": "reservation",
            "id": instance.id,
            "group_id": instance.group_id,
            "vehicle_id": instance.vehicle_id,
            "status": getattr(instance, "status", None),
            "changed_at": now().isoformat(),
        }
        _ws_broadcast("reservation.deleted", payload)

    connection_in_atomic_block = transaction.get_connection().in_atomic_block
    if connection_in_atomic_block:
        transaction.on_commit(perform_delete_side_effects_and_broadcast)
    else:
        perform_delete_side_effects_and_broadcast()



@receiver(post_save, sender=VehicleReservation)
def _auto_cleanup_payment_on_pending(
    sender: type[VehicleReservation], instance: VehicleReservation, **kwargs: Any
) -> None:
    group_obj: Optional[ReservationGroup] = instance.group
    if group_obj is None or group_obj.status != ReservationStatus.AWAITING_PAYMENT:
        return

    def perform_cleanup_and_broadcast() -> None:
        PaymentIntent.objects.filter(
            reservation_group=group_obj,
            status__in=[
                PaymentIntentStatus.REQUIRES_CONFIRMATION,
                PaymentIntentStatus.PROCESSING,
            ],
        ).update(status=PaymentIntentStatus.CANCELED)
        ReservationGroup.objects.filter(pk=group_obj.pk).update(
            status=ReservationStatus.PENDING
        )

        payload = {
            "kind": "group",
            "group_id": group_obj.id,
            "status": ReservationStatus.PENDING,
            "changed_at": now().isoformat(),
        }
        _ws_broadcast("group.status_changed", payload)

    connection_in_atomic_block = transaction.get_connection().in_atomic_block
    if connection_in_atomic_block:
        transaction.on_commit(perform_cleanup_and_broadcast)
    else:
        perform_cleanup_and_broadcast()
