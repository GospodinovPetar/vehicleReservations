from django.contrib import admin
from .models import Location, Vehicle, Reservation, User
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import CustomUser


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


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = [
        'username', 'email', 'first_name', 'last_name',
        'role', 'is_blocked_display', 'is_active', 'date_joined'
    ]
    list_filter = ['role', 'is_blocked', 'is_active', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['-date_joined']

    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {
            'fields': ('role', 'phone', 'is_blocked')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Custom Fields', {
            'fields': ('role', 'phone', 'email', 'first_name', 'last_name')
        }),
    )

    def is_blocked_display(self, obj):
        if obj.is_blocked:
            return format_html(
                '<span style="color: red;">●</span> Blocked'
            )
        return format_html(
            '<span style="color: green;">●</span> Active'
        )

    is_blocked_display.short_description = 'Status'

    actions = ['block_users', 'unblock_users', 'promote_to_manager', 'demote_to_user']

    def block_users(self, request, queryset):
        count = queryset.update(is_blocked=True)
        self.message_user(request, f'{count} users were blocked.')

    block_users.short_description = "Block selected users"

    def unblock_users(self, request, queryset):
        count = queryset.update(is_blocked=False)
        self.message_user(request, f'{count} users were unblocked.')

    unblock_users.short_description = "Unblock selected users"

    def promote_to_manager(self, request, queryset):
        count = queryset.update(role='manager')
        self.message_user(request, f'{count} users were promoted to manager.')

    promote_to_manager.short_description = "Promote to manager"

    def demote_to_user(self, request, queryset):
        count = queryset.update(role='user')
        self.message_user(request, f'{count} users were demoted to user.')

    demote_to_user.short_description = "Demote to user"
