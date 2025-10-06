from __future__ import annotations

from typing import List, Tuple, Type

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html

from .models import CustomUser
from inventory.admin import VehicleAdmin, VehicleReservationAdmin
from inventory.models.reservation import Location, VehicleReservation
from inventory.models.vehicle import Vehicle


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = [
        "id",
        "username_link",
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
        ("Custom Fields", {"fields": ("role", "phone", "email", "first_name", "last_name")}),
    )

    def username_link(self, obj: CustomUser) -> str:
        url = reverse("accounts:profile-detail", kwargs={"pk": obj.pk})
        return format_html('<a href="{}">{}</a>', url, obj.username)

    username_link.short_description = "Username"

    def is_blocked_display(self, obj: CustomUser) -> str:
        return format_html(
            '<span style="color:{};">●</span> {}',
            "red" if obj.is_blocked else "green",
            "Blocked" if obj.is_blocked else "Active",
        )

    is_blocked_display.short_description = "Status"

    actions = ["block_users", "unblock_users", "promote_to_manager", "demote_to_user"]

    def save_model(self, request: HttpRequest, obj: CustomUser, form, change: bool) -> None:
        if getattr(obj, "role", None) == "admin":
            raise ValidationError("Admins cannot be modified.")
        super().save_model(request, obj, form, change)

    def delete_model(self, request: HttpRequest, obj: CustomUser) -> None:
        if getattr(obj, "role", None) == "admin":
            raise ValidationError("Admins cannot be deleted.")
        super().delete_model(request, obj)

    def block_users(self, request: HttpRequest, queryset) -> None:
        queryset = queryset.exclude(role="admin")
        count = queryset.update(is_blocked=True)
        self.message_user(request, f"{count} users were blocked.")

    def unblock_users(self, request: HttpRequest, queryset) -> None:
        queryset = queryset.exclude(role="admin")
        count = queryset.update(is_blocked=False)
        self.message_user(request, f"{count} users were unblocked.")

    def promote_to_manager(self, request: HttpRequest, queryset) -> None:
        queryset = queryset.exclude(role="admin")
        count = queryset.update(role="manager")
        self.message_user(request, f"{count} users were promoted to manager.")

    def demote_to_user(self, request: HttpRequest, queryset) -> None:
        queryset = queryset.exclude(role="admin")
        count = queryset.update(role="user")
        self.message_user(request, f"{count} users were demoted to user.")

    def has_view_permission(self, request: HttpRequest, obj: CustomUser | None = None) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")

    def has_change_permission(self, request: HttpRequest, obj: CustomUser | None = None) -> bool:
        if obj and getattr(obj, "role", None) == "admin":
            return False
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")

    def has_delete_permission(self, request: HttpRequest, obj: CustomUser | None = None) -> bool:
        if obj and getattr(obj, "role", None) == "admin":
            return False
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")


try:
    admin.site.unregister(CustomUser)
except admin.sites.NotRegistered:
    pass
admin.site.register(CustomUser, CustomUserAdmin)


class ManagerSafeAdmin(admin.ModelAdmin):
    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") in {"admin", "manager"})

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") in {"admin", "manager"})

    def has_add_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") in {"admin", "manager"})

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") in {"admin", "manager"})

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") in {"admin", "manager"})


def wrap_with_restrictions(
    modeladmin_cls: Type[admin.ModelAdmin],
    safeadmin_cls: Type[admin.ModelAdmin],
) -> Type[admin.ModelAdmin]:
    class WrappedAdmin(modeladmin_cls):  # type: ignore[misc]
        search_fields = getattr(modeladmin_cls, "search_fields", ["id"])

        def has_module_permission(self, request: HttpRequest) -> bool:
            if getattr(request.user, "role", "") == "manager":
                return safeadmin_cls.has_module_permission(self, request)
            return modeladmin_cls.has_module_permission(self, request)

        def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
            if getattr(request.user, "role", "") == "manager":
                return safeadmin_cls.has_view_permission(self, request, obj)
            return modeladmin_cls.has_view_permission(self, request, obj)

        def has_add_permission(self, request: HttpRequest) -> bool:
            if getattr(request.user, "role", "") == "manager":
                return safeadmin_cls.has_add_permission(self, request)
            return modeladmin_cls.has_add_permission(self, request)

        def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
            if getattr(request.user, "role", "") == "manager":
                return safeadmin_cls.has_change_permission(self, request, obj)
            return modeladmin_cls.has_change_permission(self, request, obj)

        def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
            if getattr(request.user, "role", "") == "manager":
                return safeadmin_cls.has_delete_permission(self, request, obj)
            return modeladmin_cls.has_delete_permission(self, request, obj)

    return WrappedAdmin


for model, admin_cls in [
    (Vehicle, VehicleAdmin),
    (VehicleReservation, VehicleReservationAdmin),
]:
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass
    admin.site.register(model, wrap_with_restrictions(admin_cls, ManagerSafeAdmin))


class AdminOnlyAdmin(admin.ModelAdmin):
    search_fields = ["name"]

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")

    def has_view_permission(self, request: HttpRequest, obj=None) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return bool(request.user.is_authenticated and getattr(request.user, "role", "") == "admin")


try:
    admin.site.unregister(Location)
except admin.sites.NotRegistered:
    pass
admin.site.register(Location, AdminOnlyAdmin)


def custom_has_permission(request: HttpRequest) -> bool:
    return bool(request.user.is_active and getattr(request.user, "role", "") == "admin")


admin.site.has_permission = custom_has_permission
