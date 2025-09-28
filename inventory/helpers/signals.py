from __future__ import annotations

from typing import Any, List, Optional

from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from emails.send_group_created import send_group_created_email
from emails.send_group_status_changed import send_group_status_changed_email
from emails.send_reservation_edited import send_reservation_edited_email
from emails.send_vehicle_added import send_vehicle_added_email
from emails.send_vehicle_removed import send_vehicle_removed_email
from inventory.models.reservation import (
    ReservationGroup,
    VehicleReservation,
    ReservationStatus,
)
from mockpay.models import PaymentIntent, PaymentIntentStatus


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
    def perform_actions() -> None:
        if created:
            send_vehicle_added_email(instance)
            return
        before_snapshot = getattr(instance, "_before_snapshot", None)
        if before_snapshot is None:
            return
        tracked_fields: List[str] = [
            "start_date",
            "end_date",
            "pickup_location_id",
            "return_location_id",
            "vehicle_id",
        ]
        has_changed = False
        for field_name in tracked_fields:
            before_value = getattr(before_snapshot, field_name, None)
            current_value = getattr(instance, field_name, None)
            if before_value != current_value:
                has_changed = True
                break
        if has_changed:
            send_reservation_edited_email(before_snapshot, instance)

    connection_in_atomic_block = transaction.get_connection().in_atomic_block
    if connection_in_atomic_block:
        transaction.on_commit(perform_actions)
    else:
        perform_actions()


@receiver(post_delete, sender=VehicleReservation)
def _reservation_deleted(
    sender: type[VehicleReservation], instance: VehicleReservation, **kwargs: Any
) -> None:
    def perform_delete_side_effect() -> None:
        send_vehicle_removed_email(instance)

    connection_in_atomic_block = transaction.get_connection().in_atomic_block
    if connection_in_atomic_block:
        transaction.on_commit(perform_delete_side_effect)
    else:
        perform_delete_side_effect()


@receiver(post_save, sender=VehicleReservation)
def _auto_cleanup_payment_on_pending(
    sender: type[VehicleReservation], instance: VehicleReservation, **kwargs: Any
) -> None:
    group_obj: Optional[ReservationGroup] = instance.group
    if group_obj is None or group_obj.status != ReservationStatus.AWAITING_PAYMENT:
        return

    def perform_cleanup() -> None:
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

    connection_in_atomic_block = transaction.get_connection().in_atomic_block
    if connection_in_atomic_block:
        transaction.on_commit(perform_cleanup)
    else:
        perform_cleanup()
