from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q

from inventory.models.vehicle import Vehicle

BLOCKING_STATUSES = ("RESERVED", "CONFIRMED")


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name


class ReservationStatus(models.TextChoices):
    RESERVED = "RESERVED", "Reserved"
    CANCELED = "CANCELED", "Canceled"
    REJECTED = "REJECTED", "Rejected"
    COMPLETED = "COMPLETED", "Completed"
    CONFIRMED = "CONFIRMED", "Confirmed"


class Reservation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reservations"
    )
    vehicle = models.ForeignKey(
        "inventory.Vehicle", on_delete=models.PROTECT, related_name="reservations"
    )
    pickup_location = models.ForeignKey(
        "inventory.Location", on_delete=models.PROTECT, related_name="+"
    )
    return_location = models.ForeignKey(
        "inventory.Location", on_delete=models.PROTECT, related_name="+"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.RESERVED,
    )
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    group = models.ForeignKey(
        "inventory.ReservationGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )

    def clean(self):
        errors = {}

        if self.start_date and self.end_date and self.start_date >= self.end_date:
            errors["end_date"] = "End date must be after start date"

        if self.vehicle_id and self.start_date and self.end_date:
            overlapping = Reservation.objects.filter(
                vehicle_id=self.vehicle_id, status__in=BLOCKING_STATUSES
            ).filter(start_date__lt=self.end_date, end_date__gt=self.start_date)
            if self.pk:
                overlapping = overlapping.exclude(pk=self.pk)
            if overlapping.exists():
                errors["start_date"] = (
                    "Vehicle is not available in the selected period."
                )

        if errors:
            raise ValidationError(errors)

    @staticmethod
    def available_vehicles(
        start_date, end_date, pickup_location=None, return_location=None
    ):
        blocked = (
            Reservation.objects.filter(status__in=BLOCKING_STATUSES)
            .filter(start_date__lt=end_date, end_date__gt=start_date)
            .values_list("vehicle_id", flat=True)
            .distinct()
        )

        qs = Vehicle.objects.exclude(id__in=blocked)

        if pickup_location is not None:
            qs = qs.annotate(
                _pickup_cnt=Count("available_pickup_locations", distinct=True)
            ).filter(Q(_pickup_cnt=0) | Q(available_pickup_locations=pickup_location))

        if return_location is not None:
            qs = qs.annotate(
                _return_cnt=Count("available_return_locations", distinct=True)
            ).filter(Q(_return_cnt=0) | Q(available_return_locations=return_location))

        return qs.distinct().values_list("id", flat=True)

    @classmethod
    def conflicts_exist(cls, *, vehicle_id, start_date, end_date) -> bool:
        return cls.objects.filter(
            vehicle_id=vehicle_id,
            status__in=BLOCKING_STATUSES,
            start_date__lt=end_date,
            end_date__gt=start_date,
        ).exists()

    @classmethod
    def is_vehicle_available(
        cls,
        *,
        vehicle,
        start_date,
        end_date,
        pickup_location=None,
        return_location=None
    ) -> bool:
        if pickup_location and vehicle.available_pickup_locations.exists():
            if not vehicle.available_pickup_locations.filter(
                pk=pickup_location.pk
            ).exists():
                return False
        if return_location and vehicle.available_return_locations.exists():
            if not vehicle.available_return_locations.filter(
                pk=return_location.pk
            ).exists():
                return False
        return not cls.conflicts_exist(
            vehicle_id=vehicle.id, start_date=start_date, end_date=end_date
        )

    def _compute_total_price(self) -> Decimal:
        days = (self.end_date - self.start_date).days
        daily = getattr(self.vehicle, "price_per_day", Decimal("0.00")) or Decimal(
            "0.00"
        )
        return (Decimal(days) * Decimal(daily)).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        self.full_clean()
        self.total_price = self._compute_total_price()
        return super().save(*args, **kwargs)
