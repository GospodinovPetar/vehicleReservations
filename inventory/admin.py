from django.contrib import admin

from inventory.models.reservation import ReservationGroup
from inventory.models.reservation import VehicleReservation, Location
from inventory.models.vehicle import Vehicle


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("name", "price_per_day")
    search_fields = ("name",)
    filter_horizontal = ("available_pickup_locations", "available_return_locations")


class ReservationInline(admin.TabularInline):
    model = VehicleReservation
    fields = (
        "vehicle",
        "pickup_location",
        "return_location",
        "start_date",
        "end_date",
        "group_status",
        "total_price",
    )
    readonly_fields = ("group_status", "total_price")
    autocomplete_fields = ("vehicle", "pickup_location", "return_location")
    extra = 0
    show_change_link = True
    can_delete = True

    # NEW: computed column used by fields/readonly_fields above
    def group_status(self, obj):
        return getattr(obj.group, "status", "-")
    group_status.short_description = "Status"


@admin.register(ReservationGroup)
class ReservationGroupAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "created_at")
    search_fields = ("reference", "user__username")
    autocomplete_fields = ("user",)
    inlines = [ReservationInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)

        for obj in instances:
            if isinstance(obj, VehicleReservation) and form.instance.user and not obj.user_id:
                obj.user = form.instance.user
            obj.save()

        formset.save_m2m()

        for obj in formset.deleted_objects:
            obj.delete()


@admin.register(VehicleReservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
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