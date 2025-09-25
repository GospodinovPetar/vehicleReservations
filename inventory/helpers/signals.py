from __future__ import annotations

from django.db import transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from inventory.models.reservation import (
    ReservationGroup,
    VehicleReservation,
    ReservationStatus,
)
from inventory.emails import (
    send_group_created_email,
    send_group_status_changed_email,
    send_vehicle_added_email,
    send_vehicle_removed_email,
    send_reservation_edited_email,
)
from mockpay.models import PaymentIntent, PaymentIntentStatus


@receiver(pre_save, sender=ReservationGroup)
def _capture_group_old_status(sender, instance: ReservationGroup, **kwargs):
    old_status = None
    if instance.pk:
        try:
            old_status = ReservationGroup.objects.only("status").get(pk=instance.pk).status
        except ReservationGroup.DoesNotExist:
            old_status = None
    instance._old_status = old_status


@receiver(post_save, sender=ReservationGroup)
def _group_created_or_status_changed(sender, instance: ReservationGroup, created, **kwargs):
    def _do():
        if created:
            send_group_created_email(instance)
        else:
            old_status = getattr(instance, "_old_status", None)
            if old_status is not None and old_status != instance.status:
                send_group_status_changed_email(instance, old_status, instance.status)

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(_do)
    else:
        _do()


@receiver(pre_save, sender=VehicleReservation)
def _capture_reservation_snapshot(sender, instance: VehicleReservation, **kwargs):
    if not instance.pk:
        instance._before_snapshot = None
        return
    try:
        before = VehicleReservation.objects.select_related(
            "group", "vehicle", "pickup_location", "return_location"
        ).get(pk=instance.pk)
    except VehicleReservation.DoesNotExist:
        before = None
    instance._before_snapshot = before


@receiver(post_save, sender=VehicleReservation)
def _reservation_created_or_edited(sender, instance: VehicleReservation, created, **kwargs):
    def _do():
        if created:
            send_vehicle_added_email(instance)
            return
        before = getattr(instance, "_before_snapshot", None)
        if before is None:
            return
        tracked_fields = ["start_date", "end_date", "pickup_location_id", "return_location_id", "vehicle_id"]
        changed = any(
            getattr(before, f, None) != getattr(instance, f, None) for f in tracked_fields
        )
        if changed:
            send_reservation_edited_email(before, instance)

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(_do)
    else:
        _do()


@receiver(post_delete, sender=VehicleReservation)
def _reservation_deleted(sender, instance: VehicleReservation, **kwargs):
    def _do():
        send_vehicle_removed_email(instance)

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(_do)
    else:
        _do()


@receiver(post_save, sender=VehicleReservation)
def _auto_cleanup_payment_on_pending(sender, instance: VehicleReservation, **kwargs):
    grp = instance.group
    if not grp or grp.status != ReservationStatus.AWAITING_PAYMENT:
        return

    def _do():
        PaymentIntent.objects.filter(
            reservation_group=grp,
            status__in=[PaymentIntentStatus.REQUIRES_CONFIRMATION, PaymentIntentStatus.PROCESSING],
        ).update(status=PaymentIntentStatus.CANCELED)
        ReservationGroup.objects.filter(pk=grp.pk).update(status=ReservationStatus.PENDING)

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(_do)
    else:
        _do()
