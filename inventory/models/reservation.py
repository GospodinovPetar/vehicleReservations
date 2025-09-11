from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.db import models

from inventory.models.vehicle import Vehicle


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self) -> str:
        return self.name

class ReservationStatus(models.TextChoices):
    RESERVED = "reserved", "Reserved"
    AWAITING_PICKUP = "awaiting pickup", "Awaiting pickup"
    AWAITING_DROP_OFF = "awaiting drop off", "Awaiting drop off"
    REJECTED = "rejected", "Rejected"


# statuses that block new bookings for the same period/vehicle
BLOCKING_STATUSES = (
    ReservationStatus.RESERVED,
    ReservationStatus.AWAITING_PICKUP,
    ReservationStatus.AWAITING_DROP_OFF,
)


class Reservation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations"
    )
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="reservations"
    )
    pickup_location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="pickup_reservations"
    )
    return_location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="return_reservations"
    )

    start_date = models.DateField()
    end_date = models.DateField()

    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.RESERVED,
    )

    def __str__(self) -> str:
        return f"{self.vehicle} | {self.start_date} -> {self.end_date} | {self.status}"

    def clean(self) -> None:
        errors = {}

        # Dates must be valid and in order
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            errors["end_date"] = "End date must be after start date."

        # Pickup location must be allowed for the vehicle
        if self.vehicle and self.pickup_location:
            allowed_pickup = self.vehicle.available_pickup_locations.filter(
                pk=self.pickup_location
            ).exists()
            if not allowed_pickup:
                errors["pickup_location"] = (
                    "Selected pickup location is not available for this vehicle."
                )

        # Return location must be allowed for the vehicle
        if self.vehicle and self.return_location:
            allowed_return = self.vehicle.available_return_locations.filter(
                pk=self.return_location
            ).exists()
            if not allowed_return:
                errors["return_location"] = (
                    "Selected return location is not available for this vehicle."
                )

        # Overlapping active reservations block availability
        if self.vehicle and self.start_date and self.end_date:
            overlapping = (
                Reservation.objects.filter(
                    vehicle_id=self.vehicle, status__in=BLOCKING_STATUSES
                )
                .exclude(pk=self.pk)
                .filter(start_date__lt=self.end_date, end_date__gt=self.start_date)
            )
            if overlapping.exists():
                errors["start_date"] = (
                    "Vehicle is not available in the selected period."
                )

        if errors:
            raise ValidationError(errors)

    def _compute_total_price(self) -> Decimal:
        # Pricing: total = number_of_days * price_per_day
        days_count = (self.end_date - self.start_date).days
        daily_price = self.vehicle.price_per_day or Decimal("0.00")
        total = daily_price * Decimal(days_count)
        return total.quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        self.full_clean()
        self.total_price = self._compute_total_price()
        return super().save(*args, **kwargs)

    @staticmethod
    def available_vehicles(
        start_date, end_date, pickup_location=None, return_location=None
    ):
        """
        A helper to find vehicles that are free in [start_date, end_date).
        Also respects per-vehicle allowed pickup/return locations if provided.
        """
        blocked = (
            Reservation.objects.filter(status__in=BLOCKING_STATUSES)
            .filter(start_date__lt=end_date, end_date__gt=start_date)
            .values_list("vehicle_id", flat=True)
            .distinct()
        )

        vehicles = Vehicle.objects.exclude(id__in=blocked)

        if pickup_location is not None:
            vehicles = vehicles.filter(available_pickup_locations=pickup_location)

        if return_location is not None:
            vehicles = vehicles.filter(available_return_locations=return_location)

        return vehicles.distinct().values_list("id", flat=True)
