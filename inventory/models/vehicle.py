from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

GOLF_MK2_PATTERNS = (
    "vw golf 2",
    "vw golf ii",
    "vw golf mk2",
    "volkswagen golf ii",
    "volkswagen golf 2",
    "volkswagen golf mk2",
    "golf mk2",
    "golf 2",
    "golf ii",
    "golf dvoika",
    "golf dve",
    "golf2",
)


class VehicleType(models.TextChoices):
    SEDAN = "sedan", "Sedan"
    HATCHBACK = "hatchback", "Hatchback"
    SUV = "suv", "SUV"
    MOTORCYCLE = "motorcycle", "Motorcycle"
    VAN = "van", "Van"
    TRUCK = "truck", "Truck"
    COUPE = "coupe", "Coupe"
    CONVERTIBLE = "convertible", "Convertible"
    WAGON = "wagon", "Wagon"
    OTHER = "other", "Other"


SEAT_BOUNDS = {
    VehicleType.SEDAN: (2, 5),
    VehicleType.MOTORCYCLE: (1, 2),
    VehicleType.VAN: (2, 9),
    VehicleType.TRUCK: (1, 3),
    VehicleType.COUPE: (1, 2),
    VehicleType.CONVERTIBLE: (2, 4),
    VehicleType.WAGON: (2, 7),
    VehicleType.OTHER: (2, 8),
    VehicleType.SUV: (2, 5),
}


class EngineType(models.TextChoices):
    PETROL = "petrol", "Petrol"
    DIESEL = "diesel", "Diesel"
    HYBRID = "hybrid", "Hybrid"
    ELECTRIC = "electric", "Electric"
    LPG = "lpg", "LPG"
    CNG = "cng", "CNG"
    OTHER = "other", "Other"


def _is_golf_mk2(name: str) -> bool:
    normalized = (name or "").strip().casefold()
    for pattern in GOLF_MK2_PATTERNS:
        if pattern in normalized:
            return True
    return False


class Vehicle(models.Model):
    name = models.CharField(max_length=120)
    car_type = models.CharField(max_length=24, choices=VehicleType.choices, default=VehicleType.SEDAN)
    engine_type = models.CharField(max_length=24, choices=EngineType.choices, default=EngineType.PETROL)

    seats = models.PositiveIntegerField(default=4)
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    plate_number = models.CharField(max_length=32, blank=True)

    year_of_manufacturing = models.PositiveIntegerField(null=True, blank=True)
    top_speed_kmh = models.PositiveIntegerField(null=True, blank=True)
    mileage_km = models.PositiveIntegerField(null=True, blank=True)
    fuel_consumption_l_100km = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    damages = models.TextField(blank=True)
    unlimited_seats = models.BooleanField(default=False)

    available_pickup_locations = models.ManyToManyField(
        "inventory.Location", related_name="pickup_vehicles", blank=True
    )
    available_return_locations = models.ManyToManyField(
        "inventory.Location", related_name="return_vehicles", blank=True
    )

    # class Meta:
    #     constraints = [
    #         models.CheckConstraint(
    #             name="vehicle_seats_bounds_per_type",
    #             check=(
    #                 Q(unlimited_seats=True)
    #                 | (Q(car_type=VehicleType.SEDAN) & Q(seats__gte=2) & Q(seats__lte=5))
    #                 | (
    #                     Q(car_type=VehicleType.MOTORCYCLE)
    #                     & Q(seats__gte=1)
    #                     & Q(seats__lte=2)
    #                 )
    #                 | (
    #                     Q(car_type=VehicleType.)
    #                     & Q(seats__gte=2)
    #                     & Q(seats__lte=7)
    #                 )
    #                 | (Q(car_type=VehicleType.VAN) & Q(seats__gte=2) & Q(seats__lte=9))
    #                 | (
    #                     Q(car_type=VehicleType.TRUCK)
    #                     & Q(seats__gte=1)
    #                     & Q(seats__lte=3)
    #                 )
    #             ),
    #         ),
    #     ]

    def __str__(self) -> str:
        return f"{self.name} ({self.car_type}/{self.engine_type})"

    def clean(self) -> None:
        if _is_golf_mk2(self.name):
            self.unlimited_seats = True
            self.seats = None

        if self.price_per_day is None or self.price_per_day < 0:
            raise ValidationError(
                {"price_per_day": "Price per day must be zero or positive."}
            )

        super().clean()

        if self.unlimited_seats:
            if self.seats is not None:
                raise ValidationError(
                    {"seats": "Leave seats empty when unlimited seats is enabled."}
                )
            return

        if self.seats is None:
            raise ValidationError({"seats": "Seats is required."})

        if self.seats <= 0:
            raise ValidationError({"seats": "Seats must be a positive number."})

        bounds = SEAT_BOUNDS.get(self.car_type)
        if bounds is not None:
            low, high = bounds
            if self.seats < low or self.seats > high:
                raise ValidationError(
                    {
                        "seats": f"{self.car_type} must have between {low} and {high} seats (got {self.seats})."
                    }
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
