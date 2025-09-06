from django.db.models.signals import post_migrate
from .models import Vehicle, VehiclePrice
from django.db.models.signals import post_save
from django.dispatch import receiver

DEFAULT_RETURN_LOCATIONS = [
    ("Downtown Depot", "RET-001"),
    ("Airport Terminal", "RET-002"),
    ("Central Station", "RET-003"),
    ("Harbor Gate", "RET-004"),
    ("Tech Park Hub", "RET-005"),
]


@receiver(post_migrate)
def create_default_return_locations(sender, **kwargs):
    if sender.name != "inventory":
        return
    from .models import Location  # import here so models are loaded

    for name, code in DEFAULT_RETURN_LOCATIONS:
        Location.objects.update_or_create(
            code=code,
            defaults={"name": name, "is_default_return": True},
        )


@receiver(post_save, sender=Vehicle)
def sync_vehicle_prices(sender, instance: Vehicle, **kwargs):
    """Keep VehiclePrice(day/week/month) synced to Vehicle.price_per_day & currency."""
    day = instance.price_per_day
    week = day * 6
    month = day * 26
    for label, amount in [("day", day), ("week", week), ("month", month)]:
        VehiclePrice.objects.update_or_create(
            vehicle=instance,
            period_type=label,
            defaults={"amount": amount, "currency": instance.currency},
        )
