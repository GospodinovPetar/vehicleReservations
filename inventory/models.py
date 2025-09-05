
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Location(TimeStampedModel):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, unique=True)
    is_default_return = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class Vehicle(TimeStampedModel):
    TYPE_CHOICES = [("car", "Car"), ("motorbike", "Motorbike"), ("caravan", "Caravan")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)            # e.g., "VW Golf 2"
    type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    engine_type = models.CharField(max_length=40, blank=True)  # petrol/diesel/electric
    seats = models.PositiveIntegerField(null=True, blank=True)
    # fun easter egg
    unlimited_passengers = models.BooleanField(default=False)

    # pricing (manager sets per-day only)
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")

    def clean(self):
        super().clean()
        # Easter egg: VW Golf 2 -> unlimited seats
        if (self.name or '').strip().lower() == "vw golf 2":
            self.unlimited_passengers = True
            self.seats = None

        # seats must be positive if provided and not unlimited
        if not self.unlimited_passengers and self.seats is not None and self.seats <= 0:
            raise ValidationError({"seats": "Seats must be a positive number."})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    @property
    def week_price(self):
        return self.price_per_day * 6

    @property
    def month_price(self):
        return self.price_per_day * 26


class VehicleLocation(TimeStampedModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="vehicle_locations")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="vehicle_locations")
    can_pickup = models.BooleanField(default=True)
    can_return = models.BooleanField(default=True)

    class Meta:
        unique_together = ("vehicle", "location")


class VehiclePrice(TimeStampedModel):
    PERIOD_CHOICES = [("day", "Day"), ("week", "Week"), ("month", "Month")]

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="prices")
    period_type = models.CharField(max_length=5, choices=PERIOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")

    class Meta:
        unique_together = ("vehicle", "period_type")

    def __str__(self) -> str:
        return f"{self.vehicle} {self.period_type}: {self.amount} {self.currency}"


ACTIVE_STATUSES = ("PENDING", "CONFIRMED")

class Reservation(TimeStampedModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("CANCELLED", "Cancelled"),
        ("REJECTED", "Rejected"),
        ("COMPLETED", "Completed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="reservations")
    pickup_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="pickup_reservations")
    return_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="return_reservations")
    start_date = models.DateField()
    end_date = models.DateField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="PENDING")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vehicle", "start_date", "end_date"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"Res {self.id} - {self.vehicle} ({self.start_date} → {self.end_date})"

    def clean(self):
        errors = {}
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            errors["end_date"] = "End date must be after start date."

        # ensure chosen locations are allowed for the vehicle
        if self.vehicle_id and self.pickup_location_id:
            ok = self.vehicle.vehicle_locations.filter(location_id=self.pickup_location_id, can_pickup=True).exists()
            if not ok:
                errors["pickup_location"] = "This vehicle cannot be picked up from the selected location."
        if self.vehicle_id and self.return_location_id:
            ok = self.vehicle.vehicle_locations.filter(location_id=self.return_location_id, can_return=True).exists()
            if not ok:
                errors["return_location"] = "This vehicle cannot be returned to the selected location."

        # overlapping reservations (PENDING/CONFIRMED) block
        if self.vehicle_id and self.start_date and self.end_date:
            qs = Reservation.objects.filter(vehicle_id=self.vehicle_id, status__in=ACTIVE_STATUSES)                .exclude(id=self.id)                .filter(start_date__lt=self.end_date, end_date__gt=self.start_date)
            if qs.exists():
                errors["start_date"] = "Vehicle is not available in the selected period."

        if errors:
            raise ValidationError(errors)

    @staticmethod
    def available_vehicle_ids(start_date, end_date, pickup_location=None, return_location=None):
        # vehicles blocked by overlaps
        blocked = Reservation.objects.filter(status__in=ACTIVE_STATUSES)            .filter(start_date__lt=end_date, end_date__gt=start_date)            .values_list("vehicle_id", flat=True).distinct()
        from django.db.models import Q
        vqs = Vehicle.objects.exclude(id__in=blocked)
        if pickup_location:
            vqs = vqs.filter(vehicle_locations__location=pickup_location, vehicle_locations__can_pickup=True)
        if return_location:
            vqs = vqs.filter(vehicle_locations__location=return_location, vehicle_locations__can_return=True)
        return vqs.distinct().values_list("id", flat=True)
