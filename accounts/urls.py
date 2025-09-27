from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
    path("verify-email/", views.verify_email, name="verify-email"),
    path("forgot-password/", views.forgot_password_start, name="forgot-password-start"),
    path("forgot-password/confirm/", views.forgot_password_confirm, name="forgot-password-confirm"),

    path("profile/", views.profile_view, name="profile"),
    path("profile/<int:pk>/", views.profile_view, name="profile-detail"),
    path("profile/edit/", views.profile_edit, name="profile-edit"),
    path("profile/profile-change-password/", views.profile_change_password, name="profile-change-password"),

    path("admin-dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("manager-dashboard/", views.manager_dashboard, name="manager-dashboard"),

    path("admin/users/create/", views.create_user, name="admin-create-user"),
    path("admin/users/<int:pk>/edit/", views.edit_user, name="admin-edit-user"),
    path("admin/users/<int:pk>/delete/", views.delete_user, name="admin-delete-user"),
    path("admin/users/<int:pk>/block/", views.block_user, name="admin-block-user"),
    path("admin/users/<int:pk>/unblock/", views.unblock_user, name="admin-unblock-user"),
    path("admin/users/<int:pk>/promote/", views.promote_manager, name="admin-promote-manager"),
    path("admin/users/<int:pk>/demote/", views.demote_user, name="admin-demote-user"),

    path("admin/dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("admin/create/", views.create_user, name="create-user"),
    path("admin/<int:pk>/edit/", views.edit_user, name="edit-user"),
    path("admin/<int:pk>/delete/", views.delete_user, name="delete-user"),
    path("admin/<int:pk>/block/", views.block_user, name="block-user"),
    path("admin/<int:pk>/unblock/", views.unblock_user, name="unblock-user"),
    path("admin/<int:pk>/promote/", views.promote_manager, name="promote-manager"),
    path("admin/<int:pk>/demote/", views.demote_user, name="demote-user"),

    path("manager/dashboard/", views.manager_dashboard, name="manager-dashboard"),
    path("manager/vehicles/", views.manager_vehicles, name="manager-vehicles"),
    path("manager/reservations/", views.reservation_list, name="reservation-list"),

    path("vehicles/", views.vehicle_list, name="vehicle-list"),
    path("vehicles/create/", views.vehicle_create, name="vehicle-create"),
    path("vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle-edit"),
    path("vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle-delete"),

    path("reservations/", views.reservation_list, name="reservation-list"),

    path("reservations/group/<int:pk>/approve/", views.reservation_group_approve, name="reservation-group-approve"),
    path("reservations/group/<int:pk>/reject/", views.reservation_group_reject, name="reservation-group-reject"),
    path("reservation/group/<int:pk>/complete", views.reservation_group_complete, name="reservation_group_complete"),
    path("reservation/group/<int:pk>/cancel", views.reservation_cancel, name="reservation_group_cancel"),
    path("reservations/group/<int:pk>/update/", views.reservation_update, name="reservation-update"),

    path("reservations/<int:pk>/approve/", views.reservation_approve, name="reservation-approve"),
    path("reservations/<int:pk>/reject/", views.reservation_reject, name="reservation-reject"),
    path("reservations/<int:pk>/cancel/", views.reservation_cancel, name="reservation-cancel"),
    path("reservation/<int:pk>/complete", views.reservation_complete, name="reservation-complete"),

    path("my-reservations/", views.user_reservations, name="user-reservations"),

    path("locations/", views.location_list, name="location-list"),
    path("locations/create/", views.location_create, name="location-create"),
    path("locations/<int:pk>/edit/", views.location_edit, name="location-edit"),
    path("locations/<int:pk>/delete/", views.location_delete, name="location-delete"),

    path("admin/dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("admin/users/create/", views.create_user, name="admin-create-user"),
    path("admin/users/<int:pk>/edit/", views.edit_user, name="admin-edit-user"),
    path("admin/users/<int:pk>/delete/", views.delete_user, name="admin-delete-user"),
    path("admin/users/<int:pk>/block/", views.block_user, name="admin-block-user"),
    path("admin/users/<int:pk>/unblock/", views.unblock_user, name="admin-unblock-user"),
    path("admin/users/<int:pk>/promote/", views.promote_manager, name="admin-promote-manager"),
    path("admin/users/<int:pk>/demote/", views.demote_user, name="admin-demote-user"),

    path("manager/dashboard/", views.manager_dashboard, name="manager-dashboard"),
    path("manager/vehicles/", views.vehicle_list, name="vehicle-list"),
    path("manager/vehicles/create/", views.vehicle_create, name="vehicle-create"),
    path("manager/vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle-edit"),
    path("manager/vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle-delete"),

    path("manager/reservations/", views.reservation_list, name="reservation-list"),
    path("manager/reservations/<int:pk>/approve/", views.reservation_group_approve, name="reservation-group-approve"),
    path("manager/reservations/<int:pk>/reject/", views.reservation_group_reject, name="reservation-group-reject"),
    path("manager/reservations/<int:pk>/update/", views.reservation_update, name="reservation-update"),
    path("manager/reservations/reservation/<int:pk>/approve/", views.reservation_approve, name="reservation-approve"),
    path("manager/reservations/reservation/<int:pk>/reject/", views.reservation_reject, name="reservation-reject"),
    path("manager/reservations/reservation/<int:pk>/cancel/", views.reservation_cancel, name="reservation-cancel"),

    path("manager/locations/", views.location_list, name="location-list"),
    path("manager/locations/create/", views.location_create, name="location-create"),
    path("manager/locations/<int:pk>/edit/", views.location_edit, name="location-edit"),
    path("manager/locations/<int:pk>/delete/", views.location_delete, name="location-delete"),

    path("reservations/", views.user_reservations, name="user-reservations"),
    path("reservations/<int:pk>/complete/", views.reservation_complete, name="reservation-complete"),
]
