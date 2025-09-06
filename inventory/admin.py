from django.contrib import admin
from .models import Vehicle, VehiclePrice, Location, VehicleLocation, Reservation


class VehicleLocationInline(admin.TabularInline):
    model = VehicleLocation
    extra = 0


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_default_return", "created_at")
    list_filter = ("is_default_return",)
    search_fields = ("name", "code")


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "type",
        "engine_type",
        "seats",
        "unlimited_passengers",
        "price_per_day",
        "currency",
        "created_at",
    )
    list_filter = ("type", "engine_type", "unlimited_passengers")
    search_fields = ("name",)
    inlines = [VehicleLocationInline]


@admin.register(VehiclePrice)
class VehiclePriceAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "period_type", "amount", "currency", "updated_at")
    list_filter = ("period_type", "currency")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "vehicle",
        "start_date",
        "end_date",
        "status",
        "total_price",
        "currency",
        "created_at",
    )
    list_filter = ("status", "vehicle", "user")
    search_fields = ("id", "vehicle__name", "user__username")
    autocomplete_fields = ("user", "vehicle", "pickup_location", "return_location")


admin.site.register(VehicleLocation)
