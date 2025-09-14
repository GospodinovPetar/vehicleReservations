from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.apps import apps


class ReservationGroup(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservation_groups",
    )
    reference = models.CharField(max_length=32, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reference or self.pk}"


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
    cart = models.ForeignKey(
        "inventory.Cart", on_delete=models.CASCADE, related_name="items"
    )
    vehicle = models.ForeignKey("inventory.Vehicle", on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    pickup_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    return_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["start_date", "vehicle_id"]

    def clean(self):
        if not self.start_date or not self.end_date:
            raise ValidationError({"start_date": "Required", "end_date": "Required"})
        if self.start_date >= self.end_date:
            raise ValidationError({"end_date": "End date must be after start date"})

        Reservation = apps.get_model("inventory", "Reservation")
        available_ids = set(
            Reservation.available_vehicles(
                start_date=self.start_date,
                end_date=self.end_date,
                pickup_location=self.pickup_location,
                return_location=self.return_location,
            )
        )
        if self.vehicle.pk not in available_ids:
            raise ValidationError(
                {"vehicle": "This vehicle is not available for the selected period."}
            )

        overlap = CartItem.objects.filter(
            cart=self.cart,
            vehicle=self.vehicle,
            start_date__lt=self.end_date,
            end_date__gt=self.start_date,
        )
        if self.pk:
            overlap = overlap.exclude(pk=self.pk)
        if overlap.exists():
            raise ValidationError(
                {
                    "vehicle": "This vehicle already exists in your cart for overlapping dates."
                }
            )

    def __str__(self):
        return f"{self.vehicle} ({self.start_date} -> {self.end_date})"
