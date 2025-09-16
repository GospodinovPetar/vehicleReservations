from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from inventory.emails import send_reservation_created_email, send_reservation_status_changed_email
from inventory.models.reservation import Reservation


@receiver(pre_save, sender=Reservation)
def _capture_old_status(sender, instance: Reservation, **kwargs):
    """
    Grab the previous status (if any) before saving, so post_save can compare.
    """
    instance._old_status = None
    if instance.pk:
        try:
            prev = sender.objects.only("status").get(pk=instance.pk)
            instance._old_status = prev.status
        except sender.DoesNotExist:
            pass

@receiver(post_save, sender=Reservation)
def _notify_on_create_or_transition(sender, instance: Reservation, created: bool, **kwargs):
    if created:
        send_reservation_created_email(instance)
        return

    old_status = getattr(instance, "_old_status", None)
    if not old_status or old_status == instance.status:
        return

    Status = Reservation.Status
    pending = getattr(Status, "PENDING", None)
    reserved = getattr(Status, "RESERVED", None)
    rejected = getattr(Status, "REJECTED", None)

    if pending and instance.status in {reserved, rejected} and old_status == pending:
        send_reservation_status_changed_email(instance, old_status, instance.status)
