from django.conf import settings
from django.core.exceptions import ValidationError
from django.apps import apps
from django.db import models, transaction

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
        apps.get_model("inventory", "CartItem").objects.filter(cart=self).delete()

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

    def clean(self):
        """
        Cart is non-blocking for inventory. We only validate:
        - basic dates/locations
        - NO conflicts across users or reservations
        - DO prevent the SAME USER from adding the SAME VEHICLE for overlapping dates in their own cart
        """
        errors = {}

        if not self.start_date or not self.end_date:
            errors["start_date"] = "Start and end dates are required."
        elif self.start_date >= self.end_date:
            errors["start_date"] = "Start date must be before end date."

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
    def merge_or_create(cls, *, cart, vehicle, start_date, end_date, pickup_location=None, return_location=None):
        """
        Upsert-like helper:
        - Find all existing items for (cart, vehicle, pickup_location, return_location)
          that overlap OR touch the [start_date, end_date) interval.
        - If any found, merge them all (including the new range) into one continuous interval,
          repeating until no further expansion (handles chained touches).
        - Delete the old items and persist a single merged CartItem.
        - Returns the merged/created CartItem instance.
        """
        # normalize the working window
        merged_start = start_date
        merged_end = end_date

        while True:
            touching_qs = cls.objects.select_for_update().filter(
                cart=cart,
                vehicle=vehicle,
                pickup_location=pickup_location,
                return_location=return_location,
                start_date__lte=merged_end,  # touches or overlaps on the right
                end_date__gte=merged_start,  # touches or overlaps on the left
            ).order_by("start_date")

            found = list(touching_qs)
            if not found:
                break

            # Expand window to cover all touching/overlapping items
            new_start = min([merged_start] + [i.start_date for i in found])
            new_end = max([merged_end] + [i.end_date for i in found])

            if new_start == merged_start and new_end == merged_end:
                break

            merged_start, merged_end = new_start, new_end

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
