from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.db import connection
from .models import Location


DEFAULT_LOCATIONS = [
    "Downtown Depot",
    "Airport Terminal",
    "Central Station",
    "Harbor Gate",
    "Tech Park Hub",
]


@receiver(post_migrate)
def create_default_locations(sender, **kwargs):
    """
    After migrating the 'inventory' app, make sure some basic locations exist.
    Uses only the 'name' field to keep things simple.
    """
    if getattr(sender, "name", None) != "inventory":
        return

    table_names = connection.introspection.table_names()
    if Location._meta.db_table not in table_names:
        return

    for location_name in DEFAULT_LOCATIONS:
        try:
            Location.objects.get(name=location_name)
        except Location.DoesNotExist:
            Location.objects.create(name=location_name)
