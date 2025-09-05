from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Iterable, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TimeStampedModel(models.Model):
    """
    Abstract base that adds created/updated timestamps.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Location(TimeStampedModel):
    """
    A physical place where vehicles can be picked up or returned.
    """
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, unique=True)
    is_default_return = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class VehicleType(models.TextChoices):
    CAR = "car", "Car"
    MOTORBIKE = "motorbike", "Motorbike"
    CARAVAN = "caravan", "Caravan"


class Vehicle(TimeStampedModel):
    """
    A rentable vehicle.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)  # e.g., "VW Golf 2"
    type = models.CharField(max_length=12, choices=VehicleType.choices)
    engine_type = models.CharField(max_length=40, blank=True)  # petrol/diesel/electric
    seats = models.PositiveIntegerField(null=True, blank=True)
    unlimited_passengers = models.BooleanField(default=False)

    price_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="EUR")

    def clean(self) -> None:
        super().clean()

        # Validate seat count only when not unlimited and provided.
        seats_provided = self.seats is not None
        if not self.unlimited_passengers and seats_provided and self.seats <= 0:
            raise ValidationError({"seats": "Seats must be a positive number."})

    def save(self, *args, **kwargs):
        # Ensure model-level validation runs even outside ModelForms.
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    @property
    def week_price(self) -> Decimal:
        return self.price_per_day * 6

    @property
    def month_price(self) -> Decimal:
        return self.price_per_day * 26


class VehicleLocation(TimeStampedModel):
    """
    A vehicle's availability at a specific location.
    """
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="vehicle_locations"
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="vehicle_locations"
    )
    can_pickup = models.BooleanField(default=True)
    can_return = models.BooleanField(default=True)

    class Meta:
        unique_together = ("vehicle", "location")


class PricePeriod(models.TextChoices):
    DAY = "day", "Day"
    WEEK = "week", "Week"
    MONTH = "month", "Month"


class VehiclePrice(TimeStampedModel):
    """
    A concrete price for a vehicle for a specific period (day/week/month).
    """
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="prices"
    )
    period_type = models.CharField(max_length=5, choices=PricePeriod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")

    class Meta:
        unique_together = ("vehicle", "period_type")

    def __str__(self) -> str:
        return f"{self.vehicle} {self.period_type}: {self.amount} {self.currency}"


class ReservationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    CANCELLED = "CANCELLED", "Cancelled"
    REJECTED = "REJECTED", "Rejected"
    COMPLETED = "COMPLETED", "Completed"


ACTIVE_RESERVATION_STATUSES: Iterable[str] = (
    ReservationStatus.PENDING,
    ReservationStatus.CONFIRMED,
)


class Reservation(TimeStampedModel):
    """
    A booking for a vehicle within a date range, optionally tied to a user.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Make user optional while not shipping auth. Switch back to required later.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reservations",
        null=True,
        blank=True,
    )

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="reservations")
    pickup_location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="pickup_reservations"
    )
    return_location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="return_reservations"
    )

    start_date = models.DateField()
    end_date = models.DateField()

    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(
        max_length=12, choices=ReservationStatus.choices, default=ReservationStatus.PENDING
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vehicle", "start_date", "end_date"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"Reservation {self.id} - {self.vehicle} ({self.start_date} → {self.end_date})"

    def clean(self) -> None:
        """
        Validate date ordering, pickup/return availability, and reservation overlap.
        """
        validation_errors = {}

        # Dates must be in order.
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            validation_errors["end_date"] = "End date must be after start date."

        # Check pickup location is allowed for this vehicle.
        if self.vehicle_id and self.pickup_location_id:
            is_pickup_allowed = self.vehicle.vehicle_locations.filter(
                location_id=self.pickup_location_id,
                can_pickup=True,
            ).exists()
            if not is_pickup_allowed:
                validation_errors["pickup_location"] = (
                    "This vehicle cannot be picked up from the selected location."
                )

        # Check return location is allowed for this vehicle.
        if self.vehicle_id and self.return_location_id:
            is_return_allowed = self.vehicle.vehicle_locations.filter(
                location_id=self.return_location_id,
                can_return=True,
            ).exists()
            if not is_return_allowed:
                validation_errors["return_location"] = (
                    "This vehicle cannot be returned to the selected location."
                )

        # Block overlapping reservations in active statuses.
        if self.vehicle_id and self.start_date and self.end_date:
            overlapping_reservations = (
                Reservation.objects
                .filter(vehicle_id=self.vehicle_id, status__in=ACTIVE_RESERVATION_STATUSES)
                .exclude(id=self.id)
                .filter(start_date__lt=self.end_date, end_date__gt=self.start_date)
            )
            if overlapping_reservations.exists():
                validation_errors["start_date"] = (
                    "Vehicle is not available in the selected period."
                )

        if validation_errors:
            raise ValidationError(validation_errors)

    @staticmethod
    def available_vehicle_ids(
        start_date,
        end_date,
        pickup_location: Optional[Location] = None,
        return_location: Optional[Location] = None,
    ):
        """
        Return a queryset of available vehicle IDs between start_date and end_date,
        optionally constrained by pickup/return locations.
        """
        blocked_vehicle_ids = (
            Reservation.objects
            .filter(status__in=ACTIVE_RESERVATION_STATUSES)
            .filter(start_date__lt=end_date, end_date__gt=start_date)
            .values_list("vehicle_id", flat=True)
            .distinct()
        )

        vehicle_queryset = Vehicle.objects.exclude(id__in=blocked_vehicle_ids)

        if pickup_location is not None:
            vehicle_queryset = vehicle_queryset.filter(
                vehicle_locations__location=pickup_location,
                vehicle_locations__can_pickup=True,
            )

        if return_location is not None:
            vehicle_queryset = vehicle_queryset.filter(
                vehicle_locations__location=return_location,
                vehicle_locations__can_return=True,
            )

        return vehicle_queryset.distinct().values_list("id", flat=True)
