from __future__ import annotations

from typing import List, Tuple

from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import Vehicle

DEFAULT_RETURN_LOCATIONS: List[Tuple[str, str]] = [
    ("Downtown Depot", "RET-001"),
    ("Airport Terminal", "RET-002"),
    ("Central Station", "RET-003"),
    ("Harbor Gate", "RET-004"),
    ("Tech Park Hub", "RET-005"),
]


@receiver(post_migrate)
def create_default_return_locations(sender, **kwargs) -> None:
    """
    After the 'inventory' app migrates, ensure standard return locations exist.
    """
    app_name = getattr(sender, "name", None)
    if app_name != "inventory":
        return

    # Import is inside the handler so models are fully loaded.
    from .models import Location

    for default_location in DEFAULT_RETURN_LOCATIONS:
        location_name = default_location[0]
        location_code = default_location[1]

        Location.objects.update_or_create(
            code=location_code,
            defaults={"name": location_name, "is_default_return": True},
        )


@receiver(post_save, sender=Vehicle)
def sync_vehicle_prices(sender, instance: Vehicle, **kwargs) -> None:
    """
    Keep VehiclePrice (day/week/month) in sync with Vehicle.price_per_day and currency.
    """
    from .models import VehiclePrice

    day_price = instance.price_per_day
    if day_price is None:
        return

    week_price = day_price * 6
    month_price = day_price * 26

    VehiclePrice.objects.update_or_create(
        vehicle=instance,
        period_type="day",
        defaults={"amount": day_price, "currency": instance.currency},
    )

    VehiclePrice.objects.update_or_create(
        vehicle=instance,
        period_type="week",
        defaults={"amount": week_price, "currency": instance.currency},
    )

    VehiclePrice.objects.update_or_create(
        vehicle=instance,
        period_type="month",
        defaults={"amount": month_price, "currency": instance.currency},
    )
