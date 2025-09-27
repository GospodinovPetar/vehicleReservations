from django.conf import settings
from django.core.exceptions import ValidationError
from django.apps import apps
from django.db import models, transaction


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
        "inventory.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    return_location = models.ForeignKey(
        "inventory.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["start_date", "vehicle_id"]
        # DB-level guard: end_date must be after start_date
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gt=models.F("start_date")),
                name="cartitem_end_after_start",
            ),
        ]

    @staticmethod
    def _validate_dates(start_date, end_date):
        """
        Shared validation:
        - end_date must be strictly after start_date (half-open range [start, end))
        - rental length must not exceed MAX_RENTAL_DAYS
        """
        if start_date is None or end_date is None:
            raise ValidationError("Both start and end dates are required.")
        if end_date <= start_date:
            raise ValidationError("End date must be after start date.")

        max_days = _max_rental_days()
        rental_days = (end_date - start_date).days
        if rental_days > max_days:
            raise ValidationError(
                f"Rental length is too long: {rental_days} days (max {max_days})."
            )

    def clean(self):
        """
        Cart is non-blocking for inventory. We only validate:
        - basic dates/locations (+ max rental length)
        - NO conflicts across users or reservations
        - DO prevent the SAME USER from adding the SAME VEHICLE for overlapping dates in their own cart
        """
        errors = {}

        try:
            self._validate_dates(self.start_date, self.end_date)
        except ValidationError as e:
            msg = e.messages[0] if hasattr(e, "messages") and e.messages else str(e)
            errors["start_date"] = msg

        if bool(self.pickup_location) ^ bool(self.return_location):
            errors["pickup_location"] = "Pickup and return locations should both be set or both empty."

        if errors:
            raise ValidationError(errors)

        if self.cart_id and self.vehicle_id and self.start_date and self.end_date:
            overlap_exists = CartItem.objects.filter(
                cart_id=self.cart_id,
                vehicle_id=self.vehicle_id,
                start_date__lt=self.end_date,
                end_date__gt=self.start_date,
            ).exclude(pk=self.pk).exists()

            if overlap_exists:
                raise ValidationError({
                    "__all__": "This vehicle is already in your cart for overlapping dates."
                })

    @classmethod
    @transaction.atomic
    def merge_or_create(
        cls, *, cart, vehicle, start_date, end_date, pickup_location=None, return_location=None
    ):
        """
        Upsert-like helper:
        - Validate dates (end > start, <= MAX_RENTAL_DAYS)
        - Find all existing items for (cart, vehicle, pickup_location, return_location)
          that overlap OR touch the [start_date, end_date) interval.
        - If any found, merge them all into one continuous interval (handles chained touches).
        - Delete the old items and persist a single merged CartItem.
        - Returns the merged/created CartItem instance.
        """
        cls._validate_dates(start_date, end_date)

        merged_start = start_date
        merged_end = end_date

        while True:
            touching_qs = (
                cls.objects.select_for_update()
                .filter(
                    cart=cart,
                    vehicle=vehicle,
                    pickup_location=pickup_location,
                    return_location=return_location,
                    # touches or overlaps:
                    start_date__lte=merged_end,
                    end_date__gte=merged_start,
                )
                .order_by("start_date")
            )

            found = list(touching_qs)
            if not found:
                break

            new_start = min([merged_start] + [i.start_date for i in found])
            new_end = max([merged_end] + [i.end_date for i in found])

            if new_start == merged_start and new_end == merged_end:
                break

            merged_start, merged_end = new_start, new_end

        cls._validate_dates(merged_start, merged_end)

        cls.objects.filter(
            cart=cart,
            vehicle=vehicle,
            pickup_location=pickup_location,
            return_location=return_location,
            start_date__lte=merged_end,
            end_date__gte=merged_start,
        ).delete()

        merged = cls.objects.create(
            cart=cart,
            vehicle=vehicle,
            start_date=merged_start,
            end_date=merged_end,
            pickup_location=pickup_location,
            return_location=return_location,
        )
        return merged

    def __str__(self):
        return f"{self.vehicle} ({self.start_date} -> {self.end_date})"
