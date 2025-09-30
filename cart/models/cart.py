from django.conf import settings
from django.core.exceptions import ValidationError
from django.apps import apps
from django.db import models, transaction
from django.utils import timezone


def _max_rental_days() -> int:
    return int(getattr(settings, "MAX_RENTAL_DAYS", 60))  # Precaution


class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_checked_out = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_checked_out=False),
                name="one_active_cart_per_user",
            )
        ]

    def __str__(self):
        state = "checked out" if self.is_checked_out else "active"
        return f"Cart #{self.pk} for {self.user} ({state})"

    @staticmethod
    def get_or_create_active(user):
        obj, _ = Cart.objects.get_or_create(user=user, is_checked_out=False)
        return obj

    def clear(self):
        CartItem = apps.get_model("cart", "CartItem")
        with transaction.atomic():
            # Lock items (race safety) then delete
            list(
                CartItem.objects.select_for_update()
                .filter(cart=self)
                .values_list("id", flat=True)
            )
            CartItem.objects.filter(cart=self).delete()


class CartItem(models.Model):
    cart = models.ForeignKey("Cart", on_delete=models.CASCADE, related_name="items")
    vehicle = models.ForeignKey("inventory.Vehicle", on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()

    pickup_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="+",
    )
    return_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="+",
    )

    # Optional: filled later by pricing, used by API/UI for quick totals
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["start_date", "vehicle_id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gt=models.F("start_date")),
                name="cartitem_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["cart", "vehicle", "start_date", "end_date"]),
        ]

    @staticmethod
    def _validate_dates(start_date, end_date):
        if start_date is None or end_date is None:
            raise ValidationError("Both start and end dates are required.")
        if end_date <= start_date:
            raise ValidationError("End date must be after start date.")
        # Disallow past dates for better UX and to avoid later checkout failures
        today = timezone.localdate()
        if start_date < today:
            raise ValidationError("Start date cannot be in the past.")
        if end_date < today:
            raise ValidationError("End date cannot be in the past.")
        max_days = _max_rental_days()
        rental_days = (end_date - start_date).days
        if rental_days > max_days:
            raise ValidationError(
                f"Rental length is too long: {rental_days} days (max {max_days})."
            )

    def clean(self):
        errors = {}

        try:
            self._validate_dates(self.start_date, self.end_date)
        except ValidationError as e:
            msg = e.messages[0] if getattr(e, "messages", None) else str(e)
            errors["start_date"] = msg

        # Ensure both locations selected
        if not self.pickup_location or not self.return_location:
            errors["pickup_location"] = "Select both pickup and return locations."

        if errors:
            raise ValidationError(errors)

        if self.cart_id and self.vehicle_id and self.start_date and self.end_date:
            overlap_exists = (
                CartItem.objects.filter(
                    cart_id=self.cart_id,
                    vehicle_id=self.vehicle_id,
                    start_date__lt=self.end_date,
                    end_date__gt=self.start_date,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if overlap_exists:
                raise ValidationError(
                    {
                        "__all__": "This vehicle is already in your cart for overlapping dates."
                    }
                )


    def __str__(self):
        return f"{self.vehicle} ({self.start_date} -> {self.end_date})"
