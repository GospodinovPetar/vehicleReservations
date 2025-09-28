from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from inventory.models.vehicle import Vehicle
from inventory.helpers.pricing import RateTable, quote_total


class VehicleReservation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservations",
    )

    vehicle = models.ForeignKey(
        "inventory.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )
    vehicle_name_snapshot = models.CharField(max_length=200, blank=True)

    pickup_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    return_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    pickup_location_snapshot = models.CharField(max_length=200, blank=True)
    return_location_snapshot = models.CharField(max_length=200, blank=True)

    start_date = models.DateField()
    end_date = models.DateField()
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

    @property
    def vehicle_display(self) -> str:
        name_value: str = ""
        if self.vehicle_id and self.vehicle is not None:
            name_value = getattr(self.vehicle, "name", "") or str(self.vehicle) or ""
        if name_value:
            return name_value
        if self.vehicle_name_snapshot:
            return self.vehicle_name_snapshot
        return "(deleted vehicle)"

    @property
    def pickup_location_display(self) -> str:
        if self.pickup_location_id and self.pickup_location is not None:
            return self.pickup_location.name
        if self.pickup_location_snapshot:
            return self.pickup_location_snapshot
        return "(deleted location)"

    @property
    def return_location_display(self) -> str:
        if self.return_location_id and self.return_location is not None:
            return self.return_location.name
        if self.return_location_snapshot:
            return self.return_location_snapshot
        return "(deleted location)"

    def clean(self) -> None:
        super().clean()

        error_map: dict[str, str] = {}

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                error_map["end_date"] = "End date must be after start date"

        today_value = timezone.localdate()
        enforce_past_check_flag = True

        if self.pk:
            try:
                original: VehicleReservation = (
                    type(self).objects.only("start_date", "end_date").get(pk=self.pk)
                )
                enforce_past_check_flag = (
                    original.start_date != self.start_date
                    or original.end_date != self.end_date
                )
            except type(self).DoesNotExist:
                enforce_past_check_flag = True

        if enforce_past_check_flag:
            if self.start_date and self.start_date < today_value:
                error_map["start_date"] = "Pickup date cannot be in the past."
            if self.end_date and self.end_date < today_value:
                error_map["end_date"] = "Return date cannot be in the past."

        if self.vehicle_id and self.start_date and self.end_date:
            overlapping_qs = VehicleReservation.objects.filter(
                vehicle_id=self.vehicle_id,
                group__status__in=ReservationStatus.blocking(),
                start_date__lt=self.end_date,
                end_date__gt=self.start_date,
            )
            if self.pk:
                overlapping_qs = overlapping_qs.exclude(pk=self.pk)
            if overlapping_qs.exists():
                error_map["start_date"] = (
                    "Vehicle is not available in the selected period."
                )

        if len(error_map) > 0:
            raise ValidationError(error_map)

    @staticmethod
    def available_vehicles(
        start_date,
        end_date,
        pickup_location: Optional[models.Model] = None,
        return_location: Optional[models.Model] = None,
    ):
        blocked_vehicle_ids_qs = (
            VehicleReservation.objects.filter(
                group__status__in=ReservationStatus.blocking(),
                start_date__lt=end_date,
                end_date__gt=start_date,
            )
            .values_list("vehicle_id", flat=True)
            .distinct()
        )

        vehicle_qs = Vehicle.objects.exclude(id__in=blocked_vehicle_ids_qs)

        if pickup_location is not None:
            vehicle_qs = vehicle_qs.filter(
                Q(available_pickup_locations__isnull=True)
                | Q(available_pickup_locations=pickup_location)
            )

        if return_location is not None:
            vehicle_qs = vehicle_qs.filter(
                Q(available_return_locations__isnull=True)
                | Q(available_return_locations=return_location)
            )

        return vehicle_qs.distinct().values_list("id", flat=True)

    @classmethod
    def conflicts_exist(cls, vehicle: Vehicle, start_date, end_date) -> bool:
        conflict_exists_flag = cls.objects.filter(
            vehicle=vehicle,
            group__status__in=ReservationStatus.blocking(),
            start_date__lt=end_date,
            end_date__gt=start_date,
        ).exists()
        return bool(conflict_exists_flag)

    @classmethod
    def is_vehicle_available(
        cls,
        vehicle: Vehicle,
        start_date,
        end_date,
        pickup: Optional[models.Model] = None,
        ret: Optional[models.Model] = None,
    ) -> bool:
        if pickup is not None and vehicle.available_pickup_locations.exists():
            allowed_pickup = vehicle.available_pickup_locations.filter(
                pk=pickup.pk
            ).exists()
            if not allowed_pickup:
                return False

        if ret is not None and vehicle.available_return_locations.exists():
            allowed_return = vehicle.available_return_locations.filter(
                pk=ret.pk
            ).exists()
            if not allowed_return:
                return False

        has_conflict_flag = cls.conflicts_exist(vehicle, start_date, end_date)
        return not has_conflict_flag

    def _compute_total_price(self) -> Decimal:
        if not self.start_date or not self.end_date or not self.vehicle_id:
            return Decimal("0.00")

        vehicle_day_rate_value = float(getattr(self.vehicle, "price_per_day", 0) or 0)
        rate_table_obj = RateTable(day=vehicle_day_rate_value, currency="EUR")
        quote_dict = quote_total(
            start_date=self.start_date,
            end_date=self.end_date,
            rate_table=rate_table_obj,
        )
        total_as_decimal = Decimal(str(quote_dict.get("total", 0.0)))
        return total_as_decimal

    def save(self, *args, **kwargs):
        self.full_clean()

        computed_total = self._compute_total_price()
        self.total_price = computed_total

        if self.vehicle_id and self.vehicle is not None:
            vehicle_name_value = (
                getattr(self.vehicle, "name", "") or str(self.vehicle) or ""
            )
            if vehicle_name_value:
                self.vehicle_name_snapshot = vehicle_name_value

        if self.pickup_location_id and self.pickup_location is not None:
            self.pickup_location_snapshot = self.pickup_location.name

        if self.return_location_id and self.return_location is not None:
            self.return_location_snapshot = self.return_location.name

        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        start_str = str(self.start_date)
        end_str = str(self.end_date)
        return f"{self.vehicle_display} ({start_str} -> {end_str})"


class ReservationStatus(models.TextChoices):
    RESERVED = "RESERVED", "Reserved"
    CANCELED = "CANCELED", "Canceled"
    REJECTED = "REJECTED", "Rejected"
    COMPLETED = "COMPLETED", "Completed"
    PENDING = "PENDING", "Pending"
    AWAITING_PAYMENT = "AWAITING_PAYMENT", "Awaiting payment"

    @classmethod
    def blocking(cls) -> list[str]:
        return [cls.RESERVED, cls.PENDING, cls.AWAITING_PAYMENT]


class ReservationGroup(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservation_groups",
    )
    reference = models.CharField(max_length=32, unique=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def apply_vehicle_location_flip(self) -> None:
        items_qs = VehicleReservation.objects.filter(group=self).select_related(
            "vehicle",
            "pickup_location",
            "return_location",
        )
        for item in items_qs:
            vehicle_obj: Optional[Vehicle] = item.vehicle
            if vehicle_obj is None:
                continue
            if item.return_location_id:
                vehicle_obj.available_pickup_locations.set([item.return_location_id])
            if item.pickup_location_id:
                vehicle_obj.available_return_locations.add(item.pickup_location_id)

    @property
    def total_price(self) -> Decimal:
        aggregation = self.reservations.aggregate(s=Sum("total_price"))
        value = aggregation.get("s")
        if value is None:
            return Decimal("0.00")
        return value

    def mark_completed(self, save: bool = True) -> None:
        if self.status == ReservationStatus.COMPLETED:
            return
        self.status = ReservationStatus.COMPLETED
        if save:
            self.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        previous_status_value: Optional[str] = None
        if self.pk:
            try:
                previous_obj: ReservationGroup = (
                    type(self).objects.only("status").get(pk=self.pk)
                )
                previous_status_value = previous_obj.status
            except type(self).DoesNotExist:
                previous_status_value = None

        result = super().save(*args, **kwargs)

        status_changed_flag = previous_status_value != self.status
        if status_changed_flag and self.status == ReservationStatus.COMPLETED:
            self.apply_vehicle_location_flip()

        return result

    def __str__(self) -> str:
        return f"{self.reference or self.pk}"


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self) -> str:
        return self.name
