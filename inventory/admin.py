from django.contrib import admin
from .models import Location, Vehicle, Reservation


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "car_type",
        "engine_type",
        "seats",
        "unlimited_seats",
        "price_per_day",
    )
    list_filter = ("car_type", "engine_type", "unlimited_seats")
    search_fields = ("name",)

    # Manage allowed locations
    filter_horizontal = ("available_pickup_locations", "available_return_locations")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "vehicle",
        "pickup_location",
        "return_location",
        "start_date",
        "end_date",
        "status",
        "total_price",
    )
    list_filter = ("status", "vehicle", "user")
    search_fields = ("id", "vehicle__name", "user__username")

    # Easy FK pickers
    autocomplete_fields = ("user", "vehicle", "pickup_location", "return_location")
