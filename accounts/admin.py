from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.contrib.auth import get_user_model

from inventory.models.vehicle import Vehicle
from inventory.models.reservation import Reservation, Location

CustomUser = get_user_model()


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
        if obj.is_blocked:
            return format_html('<span style="color: red;">●</span> Blocked')
        return format_html('<span style="color: green;">●</span> Active')

    is_blocked_display.short_description = "Status"

    actions = ["block_users", "unblock_users", "promote_to_manager", "demote_to_user"]

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

    # Prevent touching admins at all
    def save_model(self, request, obj, form, change):
        if obj.role == "admin" and request.user.role != "admin":
            raise ValidationError("You cannot modify another admin.")
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        if obj.role == "admin" and request.user.role != "admin":
            raise ValidationError("You cannot delete another admin.")
        super().delete_model(request, obj)

    # Permissions: only admins can access this model
    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role == "admin"

    def has_change_permission(self, request, obj=None):
        if obj and obj.role == "admin" and request.user.role != "admin":
            return False
        return request.user.role == "admin"

    def has_delete_permission(self, request, obj=None):
        if obj and obj.role == "admin" and request.user.role != "admin":
            return False
        return request.user.role == "admin"

    def has_add_permission(self, request):
        return request.user.role == "admin"


admin.site.register(CustomUser, CustomUserAdmin)


# Managers can only access Vehicle & Reservation in Django Admin
class ManagerSafeAdmin(admin.ModelAdmin):
    """Managers can view/add/change/delete, admins full control, users none."""

    def has_module_permission(self, request):
        return request.user.role in ["admin", "manager"]

    def has_view_permission(self, request, obj=None):
        return request.user.role in ["admin", "manager"]

    def has_add_permission(self, request):
        return request.user.role in ["admin", "manager"]

    def has_change_permission(self, request, obj=None):
        return request.user.role in ["admin", "manager"]

    def has_delete_permission(self, request, obj=None):
        return request.user.role in ["admin", "manager"]


# Register with limited access
admin.site.register(Vehicle, ManagerSafeAdmin)
admin.site.register(Reservation, ManagerSafeAdmin)


# Admin-only access for Locations
class AdminOnlyAdmin(admin.ModelAdmin):
    """Only admins can manage Locations."""

    def has_module_permission(self, request):
        return request.user.role == "admin"

    def has_view_permission(self, request, obj=None):
        return request.user.role == "admin"

    def has_add_permission(self, request):
        return request.user.role == "admin"

    def has_change_permission(self, request, obj=None):
        return request.user.role == "admin"

    def has_delete_permission(self, request, obj=None):
        return request.user.role == "admin"


admin.site.register(Location, AdminOnlyAdmin)


# Admin site login restricted to admins and managers only
def custom_has_permission(request):
    """Allow admins full access, managers limited access, block normal users."""
    return request.user.is_active and request.user.role in ["admin", "manager"]


admin.site.has_permission = custom_has_permission
