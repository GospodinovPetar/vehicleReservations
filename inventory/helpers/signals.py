from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.db import transaction

from inventory.emails import send_group_status_changed_email, send_vehicle_added_email, send_reservation_created_email, \
    send_reservation_status_changed_email
from inventory.models.reservation import ReservationGroup, VehicleReservation


@receiver(pre_save, sender=ReservationGroup)
def _capture_group_old_status(sender, instance: ReservationGroup, **kwargs):
    instance._old_status = None
    if instance.pk:
        try:
            prev = sender.objects.only("status").get(pk=instance.pk)
            instance._old_status = prev.status
        except sender.DoesNotExist:
            pass

@receiver(post_save, sender=ReservationGroup)
def _notify_group_status_change(sender, instance: ReservationGroup, created: bool, **kwargs):
    if created:
        return
    old_status = getattr(instance, "_old_status", None)
    if old_status is None or old_status == instance.status:
        return
    transaction.on_commit(lambda: send_group_status_changed_email(instance, old_status, instance.status))

@receiver(post_save, sender=VehicleReservation)
def _notify_on_create_or_transition(sender, instance: VehicleReservation, created: bool, **kwargs):
    if created:
        transaction.on_commit(lambda: send_reservation_created_email(instance))
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status is None or old_status == instance.status:
        return

    transaction.on_commit(
        lambda: send_reservation_status_changed_email(instance, old_status, instance.status)
    )