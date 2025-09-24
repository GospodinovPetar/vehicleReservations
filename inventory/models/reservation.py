from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from inventory.models.vehicle import Vehicle
from inventory.helpers.pricing import RateTable, quote_total


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name


class ReservationStatus(models.TextChoices):
    RESERVED = "RESERVED", "Reserved"
    CANCELED = "CANCELED", "Canceled"
    REJECTED = "REJECTED", "Rejected"
    COMPLETED = "COMPLETED", "Completed"
    PENDING = "PENDING", "Pending"
    AWAITING_PAYMENT = "AWAITING_PAYMENT", "Awaiting payment"

    @classmethod
    def blocking(cls):
        return cls.RESERVED, cls.PENDING


BLOCKING_STATUSES = (ReservationStatus.RESERVED, ReservationStatus.PENDING)

class ReservationGroup(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservation_groups",
    )
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING,
    )
    reference = models.CharField(max_length=32, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reference or self.pk}"

class VehicleReservation(models.Model):
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
        default=ReservationStatus.PENDING,
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
        super().clean()

        errors = {}

        if self.start_date and self.end_date and self.start_date >= self.end_date:
            errors["end_date"] = "End date must be after start date"

        today = timezone.localdate()
        enforce_past_check = True
        if self.pk:
            try:
                orig = type(self).objects.only("start_date", "end_date").get(pk=self.pk)
                enforce_past_check = (
                    orig.start_date != self.start_date or orig.end_date != self.end_date
                )
            except type(self).DoesNotExist:
                enforce_past_check = True

        if enforce_past_check:
            if self.start_date and self.start_date < today:
                errors["start_date"] = "Pickup date cannot be in the past."
            if self.end_date and self.end_date < today:
                errors["end_date"] = "Return date cannot be in the past."

        if self.vehicle_id and self.start_date and self.end_date:
            overlapping = (
                VehicleReservation.objects.filter(
                    vehicle_id=self.vehicle_id,
                    status__in=BLOCKING_STATUSES,
                    start_date__lt=self.end_date,
                    end_date__gt=self.start_date,
                ).exclude(pk=self.pk)
                if self.pk
                else VehicleReservation.objects.filter(
                    vehicle_id=self.vehicle_id,
                    status__in=BLOCKING_STATUSES,
                    start_date__lt=self.end_date,
                    end_date__gt=self.start_date,
                )
            )
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
        blocked_vehicle_ids = (
            VehicleReservation.objects.filter(
                status__in=BLOCKING_STATUSES,
                group__status__in=BLOCKING_STATUSES,
                start_date__lt=end_date,
                end_date__gt=start_date,
            )
            .values_list("vehicle_id", flat=True)
            .distinct()
        )

        qs = Vehicle.objects.exclude(id__in=blocked_vehicle_ids)

        if pickup_location is not None:
            qs = qs.filter(
                Q(available_pickup_locations__isnull=True)
                | Q(available_pickup_locations=pickup_location)
            )

        if return_location is not None:
            qs = qs.filter(
                Q(available_return_locations__isnull=True)
                | Q(available_return_locations=return_location)
            )

        return qs.distinct().values_list("id", flat=True)

    @classmethod
    def conflicts_exist(cls, vehicle, start_date, end_date):
        return cls.objects.filter(
            vehicle=vehicle,
            status__in=BLOCKING_STATUSES,
            start_date__lt=end_date,
            end_date__gt=start_date,
        ).exists()

    @classmethod
    def is_vehicle_available(cls, vehicle, start_date, end_date, pickup=None, ret=None):
        if pickup is not None and vehicle.available_pickup_locations.exists():
            allowed = vehicle.available_pickup_locations.filter(pk=pickup.pk).exists()
            if not allowed:
                return False

        if ret is not None and vehicle.available_return_locations.exists():
            allowed = vehicle.available_return_locations.filter(pk=ret.pk).exists()
            if not allowed:
                return False

        has_conflict = cls.conflicts_exist(vehicle, start_date, end_date)
        return not has_conflict

    def _compute_total_price(self) -> Decimal:
        if not (self.start_date and self.end_date and self.vehicle_id):
            return Decimal("0.00")

        day_rate = float(getattr(self.vehicle, "price_per_day", 0) or 0)
        quote = quote_total(
            start_date=self.start_date,
            end_date=self.end_date,
            rate_table=RateTable(day=day_rate, currency="EUR"),
        )
        return Decimal(str(quote["total"]))

    def save(self, *args, **kwargs):
        self.full_clean()
        self.total_price = self._compute_total_price()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vehicle} ({self.start_date} -> {self.end_date})"
