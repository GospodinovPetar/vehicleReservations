from django.conf import settings
from django.core.exceptions import ValidationError
from django.apps import apps
from django.db import models, transaction
from datetime import timedelta


def _max_rental_days() -> int:
    """
    Global cap for a single rental length.
    Configure via settings.MAX_RENTAL_DAYS (default: 60).
    """
    return int(getattr(settings, "MAX_RENTAL_DAYS", 60))


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
                fields=["user", "is_checked_out"],
                name="unique_active_cart_per_user",
                condition=models.Q(is_checked_out=False),
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
        """
        Atomically remove all items from this cart.
        Uses a short row lock to serialize with concurrent checkout/cleanup.
        """
        CartItem = apps.get_model("cart", "CartItem")
        with transaction.atomic():
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
    end_date = models.DateField()  # half-open interval: [start_date, end_date)
    pickup_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="pickup_cart_items",
    )
    return_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="return_cart_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # DB-level guard to ensure end > start (portable & cheap)
            models.CheckConstraint(
                check=models.Q(end_date__gt=models.F("start_date")),
                name="cartitem_end_after_start",
            ),
            models.UniqueConstraint(
                fields=[
                    "cart",
                    "vehicle",
                    "start_date",
                    "end_date",
                    "pickup_location",
                    "return_location",
                ],
                name="unique_exact_cart_item_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "cart",
                    "vehicle",
                    "pickup_location",
                    "return_location",
                    "start_date",
                    "end_date",
                ]
            )
        ]

    def clean(self):
        """
        App-level validation for cases the DB cannot express:
        - end_date must be strictly after start_date (friendly error message)
        - rental length must not exceed MAX_RENTAL_DAYS
        """
        if self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date.")

        max_days = _max_rental_days()
        # Number of chargeable days in the half-open window
        rental_days = (self.end_date - self.start_date).days
        if rental_days > max_days:
            raise ValidationError(
                f"Rental length is too long: {rental_days} days (max {max_days})."
            )

    @staticmethod
    @transaction.atomic
    def upsert_merge(
        *,
        cart: Cart,
        vehicle,
        start_date,
        end_date,
        pickup_location,
        return_location,
    ):
        if end_date <= start_date:
            raise ValidationError("End date must be after start date.")
        max_days = _max_rental_days()
        rental_days = (end_date - start_date).days
        if rental_days > max_days:
            raise ValidationError(
                f"Rental length is too long: {rental_days} days (max {max_days})."
            )

        CartItem = apps.get_model("cart", "CartItem")

        merged_start = start_date
        merged_end = end_date

        while True:
            touching_qs = (
                CartItem.objects.select_for_update()
                .filter(
                    cart=cart,
                    vehicle=vehicle,
                    pickup_location=pickup_location,
                    return_location=return_location,
                    start_date__lt=merged_end,
                    end_date__gt=merged_start,
                )
                .order_by("start_date")
            )
            existing = list(touching_qs)
            if not existing:
                break

            for it in existing:
                if it.start_date < merged_start:
                    merged_start = it.start_date
                if it.end_date > merged_end:
                    merged_end = it.end_date

            touching_qs.delete()

        # Final guard after merging (in case chained ranges push past max)
        final_days = (merged_end - merged_start).days
        if final_days > max_days:
            raise ValidationError(
                f"Combined rental length is too long after merge: {final_days} days (max {max_days})."
            )

        merged = CartItem.objects.create(
            cart=cart,
            vehicle=vehicle,
            start_date=merged_start,
            end_date=merged_end,
            pickup_location=pickup_location,
            return_location=return_location,
        )
        return merged

    @staticmethod
    @transaction.atomic
    def merge_or_create(
        cart,
        vehicle,
        start_date,
        end_date,
        pickup_location,
        return_location,
    ):
        return CartItem.upsert_merge(
            cart=cart,
            vehicle=vehicle,
            start_date=start_date,
            end_date=end_date,
            pickup_location=pickup_location,
            return_location=return_location,
        )

    def __str__(self):
        return f"{self.vehicle} ({self.start_date} → {self.end_date})"
