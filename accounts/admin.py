from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import CustomUser
from django.shortcuts import redirect
from django.urls import reverse


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
            return format_html('<span style="color: red;">●</span> Blocked')
        return format_html('<span style="color: green;">●</span> Active')

    is_blocked_display.short_description = 'Status'

    actions = [
        'block_users',
        'unblock_users',
        'promote_to_manager',
        'demote_to_user',
        'block_and_redirect'  # new action
    ]

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

    # New admin action
    def block_and_redirect(self, request, queryset):
        queryset.update(is_blocked=True)
        self.message_user(request,
                          "Selected users were blocked and will be redirected to the 'Blocked' page on next login.")

    block_and_redirect.short_description = "Block users (redirect to Blocked page)"
