from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from inventory.models.vehicle import Vehicle
from inventory.models.reservation import Reservation, Location
from inventory.admin import VehicleAdmin, ReservationAdmin

CustomUser = get_user_model()


# === CUSTOM USER ADMIN (admins only) ===
class CustomUserAdmin(UserAdmin):
    list_display = [
        "username",
        "email",
        "first_name",
        "last_name",
        "role",
        "is_blocked_display",
        "is_active",
        "date_joined",
    ]
    list_filter = ["role", "is_blocked", "is_active", "date_joined"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]

    fieldsets = UserAdmin.fieldsets + (
        ("Custom Fields", {"fields": ("role", "phone", "is_blocked")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Custom Fields",
            {"fields": ("role", "phone", "email", "first_name", "last_name")},
        ),
    )

    def is_blocked_display(self, obj):
        return format_html(
            '<span style="color:{};">●</span> {}',
            "red" if obj.is_blocked else "green",
            "Blocked" if obj.is_blocked else "Active",
        )

    is_blocked_display.short_description = "Status"

    actions = ["block_users", "unblock_users", "promote_to_manager", "demote_to_user"]

    # === Protect admins fully (even from other admins) ===
    def save_model(self, request, obj, form, change):
        if obj.role == "admin":
            raise ValidationError("Admins cannot be modified.")
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        if obj.role == "admin":
            raise ValidationError("Admins cannot be deleted.")
        super().delete_model(request, obj)

    def block_users(self, request, queryset):
        queryset = queryset.exclude(role="admin")  # never block admins
        count = queryset.update(is_blocked=True)
        self.message_user(request, f"{count} users were blocked.")

    def unblock_users(self, request, queryset):
        queryset = queryset.exclude(role="admin")
        count = queryset.update(is_blocked=False)
        self.message_user(request, f"{count} users were unblocked.")

    def promote_to_manager(self, request, queryset):
        queryset = queryset.exclude(role="admin")
        count = queryset.update(role="manager")
        self.message_user(request, f"{count} users were promoted to manager.")

    def demote_to_user(self, request, queryset):
        queryset = queryset.exclude(role="admin")
        count = queryset.update(role="user")
        self.message_user(request, f"{count} users were demoted to user.")

    # Only admins can manage users (but even they can't touch other admins)
    def has_view_permission(self, request, obj=None):
        # Let admins always view
        if request.user.is_authenticated and request.user.role == "admin":
            return True

        # Managers can view (needed for autocomplete)
        if request.user.is_authenticated and request.user.role == "manager":
            return True

        # Default deny
        return Fals

    def has_change_permission(self, request, obj=None):
        if obj and obj.role == "admin":
            return False
        return request.user.role == "admin"

    def has_delete_permission(self, request, obj=None):
        if obj and obj.role == "admin":
            return False
        return request.user.role == "admin"

    def has_add_permission(self, request):
        return request.user.role == "admin"


# unregister first, then register
try:
    admin.site.unregister(CustomUser)
except admin.sites.NotRegistered:
    pass
admin.site.register(CustomUser, CustomUserAdmin)


# === MANAGER SAFE ADMIN (for vehicles & reservations) ===
class ManagerSafeAdmin(admin.ModelAdmin):
    """Managers can view/add/change/delete, admins full control, users none."""

    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.role in [
            "admin",
            "manager",
        ]

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role in [
            "admin",
            "manager",
        ]

    def has_add_permission(self, request):
        return request.user.is_authenticated and request.user.role in [
            "admin",
            "manager",
        ]

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role in [
            "admin",
            "manager",
        ]

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role in [
            "admin",
            "manager",
        ]


def wrap_with_restrictions(modeladmin_cls, safeadmin_cls):
    """Return a ModelAdmin that adapts behavior based on user role."""

    class WrappedAdmin(modeladmin_cls):
        # Preserve search_fields so autocomplete_fields work
        search_fields = getattr(modeladmin_cls, "search_fields", ["id"])

        def has_module_permission(self, request):
            return safeadmin_cls.has_module_permission(self, request)

        def has_view_permission(self, request, obj=None):
            return safeadmin_cls.has_view_permission(self, request, obj)

        def has_add_permission(self, request):
            return safeadmin_cls.has_add_permission(self, request)

        def has_change_permission(self, request, obj=None):
            return safeadmin_cls.has_change_permission(self, request, obj)

        def has_delete_permission(self, request, obj=None):
            return safeadmin_cls.has_delete_permission(self, request, obj)

    return WrappedAdmin


# unregister and re-register with restrictions
for model, admin_cls in [(Vehicle, VehicleAdmin), (Reservation, ReservationAdmin)]:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass
    admin.site.register(model, wrap_with_restrictions(admin_cls, ManagerSafeAdmin))


# === ADMIN-ONLY LOCATIONS ===
class AdminOnlyAdmin(admin.ModelAdmin):
    """Only admins can manage Locations."""

    search_fields = ["name"]

    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.role == "admin"

    def has_view_permission(self, request, obj=None):
        # Managers need read-only access for autocomplete
        return request.user.is_authenticated and request.user.role in ["admin", "manager"]

    def has_add_permission(self, request):
        return request.user.is_authenticated and request.user.role == "admin"

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role == "admin"

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role == "admin"


try:
    admin.site.unregister(Location)
except admin.sites.NotRegistered:
    pass
admin.site.register(Location, AdminOnlyAdmin)


# === ADMIN SITE ENTRY RESTRICTION ===
def custom_has_permission(request):
    """Admins → full access. Managers → limited. Users → no access."""
    return request.user.is_active and request.user.role in ["admin", "manager"]


admin.site.has_permission = custom_has_permission
