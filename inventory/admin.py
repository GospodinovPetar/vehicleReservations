from django.contrib import admin

from inventory.models.reservation import ReservationGroup, VehicleReservation, Location
from inventory.models.vehicle import Vehicle


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("name", "plate_number", "price_per_day")
    search_fields = ("name", "plate_number")
    filter_horizontal = ("available_pickup_locations", "available_return_locations")


class VehicleReservationInline(admin.TabularInline):
    model = VehicleReservation
    extra = 0
    autocomplete_fields = ("vehicle", "pickup_location", "return_location")
    readonly_fields = ("total_price",)


@admin.register(ReservationGroup)
class ReservationGroupAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "user__username", "user__email")
    date_hierarchy = "created_at"
    inlines = [VehicleReservationInline]


@admin.register(VehicleReservation)
class VehicleReservationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "vehicle",
        "pickup_location",
        "return_location",
        "start_date",
        "end_date",
        "group_status",
        "total_price",
        "group",
    )
    list_filter = ("group__status", "vehicle", "user")

    def group_status(self, obj):
        return getattr(obj.group, "status", "-")
    group_status.short_description = "Status"
    group_status.admin_order_field = "group__status"
