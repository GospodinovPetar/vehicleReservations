from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.db import transaction

from inventory.emails import (
    send_reservation_created_email,
    send_reservation_status_changed_email, send_vehicle_removed_email, send_vehicle_updated_email,
    send_group_status_changed_email,
)
from inventory.models.reservation import VehicleReservation, ReservationStatus


@receiver(pre_save, sender=VehicleReservation)
def _capture_old_status(sender, instance: VehicleReservation, **kwargs):

    instance._old_status = None
    instance._old_snapshot = None
    if instance.pk:
        # Snapshot selected fields to detect changes
        try:
            old = VehicleReservation.objects.get(pk=instance.pk)
            instance._old_snapshot = {
                'vehicle_id': old.vehicle_id,
                'pickup_location_id': old.pickup_location_id,
                'return_location_id': old.return_location_id,
                'start_date': old.start_date,
                'end_date': old.end_date,
            }
        except VehicleReservation.DoesNotExist:
            instance._old_snapshot = None

        try:
            prev = sender.objects.only("status").get(pk=instance.pk)
            instance._old_status = prev.status
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender=VehicleReservation)
def _notify_on_create_or_transition(
    sender, instance: VehicleReservation, created: bool, **kwargs
):
    if created:
        transaction.on_commit(lambda: send_reservation_created_email(instance))
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status is None or old_status == instance.status:
        return

    transaction.on_commit(
        lambda: send_reservation_status_changed_email(
            instance, old_status, instance.status
        )
    )


@receiver(post_delete, sender=VehicleReservation)
def _on_reservation_deleted(sender, instance: VehicleReservation, **kwargs):
    # Notify user when a vehicle is removed from a reservation
    try:
        send_vehicle_removed_email(instance)
    except Exception:
        pass

@receiver(post_save, sender=VehicleReservation)
def _on_reservation_saved(sender, instance: VehicleReservation, created, **kwargs):
    if created:
        return
    changed_fields = []
    old = getattr(instance, "_old_snapshot", None)
    if old is not None:
        if old['vehicle_id'] != instance.vehicle_id: changed_fields.append("vehicle")
        if old['pickup_location_id'] != instance.pickup_location_id: changed_fields.append("pickup_location")
        if old['return_location_id'] != instance.return_location_id: changed_fields.append("return_location")
        if old['start_date'] != instance.start_date: changed_fields.append("start_date")
        if old['end_date'] != instance.end_date: changed_fields.append("end_date")
    if changed_fields:
        try:
            send_vehicle_updated_email(instance, changed_fields)
        except Exception:
            pass
        # If group is RESERVED, flip to PENDING
        grp = getattr(instance, "group", None)
        try:
            reserved = getattr(ReservationStatus, "RESERVED", "RESERVED")
            pending = getattr(ReservationStatus, "PENDING", "PENDING")
            if grp and getattr(grp, "status", None) == reserved:
                old_status = grp.status
                grp.status = pending
                grp.save(update_fields=["status"])
                send_group_status_changed_email(grp, old_status, grp.status)
        except Exception:
            pass
