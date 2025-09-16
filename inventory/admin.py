from django.contrib import admin

from inventory.models.cart import ReservationGroup
from inventory.models.reservation import Reservation, Location
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
    model = Reservation
    fields = (
        "vehicle",
        "pickup_location",
        "return_location",
        "start_date",
        "end_date",
        "status",
        "total_price",
    )
    readonly_fields = ("total_price",)
    autocomplete_fields = ("vehicle", "pickup_location", "return_location")
    extra = 0
    show_change_link = True
    can_delete = True


@admin.register(ReservationGroup)
class ReservationGroupAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "created_at")
    search_fields = ("reference", "user__username")
    autocomplete_fields = ("user",)
    inlines = [ReservationInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)

        for obj in instances:
            if isinstance(obj, Reservation) and form.instance.user and not obj.user_id:
                obj.user = form.instance.user
            obj.save()

        formset.save_m2m()

        for obj in formset.deleted_objects:
            obj.delete()


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
        "group",
    )
    list_filter = ("status", "vehicle", "user")
    search_fields = ("id", "vehicle__name", "user__username")
    autocomplete_fields = (
        "user",
        "vehicle",
        "pickup_location",
        "return_location",
        "group",
    )
