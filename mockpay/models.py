from django.db import models
from django.utils import timezone

from inventory.models.reservation import ReservationGroup, ReservationStatus


def default_expires_at():
    return timezone.now() + timezone.timedelta(minutes=30)


class PaymentIntentStatus(models.TextChoices):
    REQUIRES_CONFIRMATION = "requires_confirmation", "Requires confirmation"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    CANCELED = "canceled", "Canceled"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"


class PaymentIntent(models.Model):
    reservation_group = models.ForeignKey(
        ReservationGroup, on_delete=models.PROTECT, related_name="payment_intents"
    )
    amount = models.PositiveIntegerField(
        help_text="Amount in the smallest currency unit (e.g. cents)"
    )
    currency = models.CharField(max_length=3, default="EUR")
    client_secret = models.CharField(max_length=96, unique=True)
    status = models.CharField(
        max_length=32,
        choices=PaymentIntentStatus.choices,
        default=PaymentIntentStatus.REQUIRES_CONFIRMATION,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(default=default_expires_at)

    class Meta:
        indexes = [models.Index(fields=["client_secret"])]

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def mark_group(self, new_status: str):
        grp = self.reservation_group
        if grp.status != new_status:
            old = grp.status
            grp.status = new_status
            grp.save(update_fields=["status"])
