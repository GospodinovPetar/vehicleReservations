from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from inventory.models.reservation import ReservationGroup
from inventory.emails import (
    send_group_created_email,
    send_group_status_changed_email,
)


@receiver(pre_save, sender=ReservationGroup)
def _capture_group_old_status(sender, instance: ReservationGroup, **kwargs):
    """
    Cache the previous status on the instance so we can compare post-save.
    """
    instance._old_status = None
    if instance.pk:
        try:
            prev = sender.objects.only("status").get(pk=instance.pk)
            instance._old_status = prev.status
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender=ReservationGroup)
def _notify_group_created_or_status_changed(
    sender, instance: ReservationGroup, created: bool, **kwargs
):
    """
    - On group creation: send ONE 'reservation_created' email (group-scoped).
    - On status change: choose the most specific template
      (reservation_confirmed / reservation_rejected) and fall back to
      reservation_status_changed.
    """
    if created:
        transaction.on_commit(lambda: send_group_created_email(instance))
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status is None or old_status == instance.status:
        return

    transaction.on_commit(
        lambda: send_group_status_changed_email(instance, old_status, instance.status)
    )
