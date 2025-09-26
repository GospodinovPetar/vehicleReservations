from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
    # Profile routes
    path("profile/", views.profile_view, name="profile"),  # always logged-in user's profile
    path("profile/<int:pk>/", views.profile_view, name="profile-detail"),  # staff can view others
    path("profile/edit/", views.profile_edit, name="profile-edit"),
    path("profile/change-password/", views.profile_change_password, name="profile-change-password"),
    # Dashboards
    path("admin-dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("manager-dashboard/", views.manager_dashboard, name="manager-dashboard"),
    # Admin user CRUD + actions
    path("admin/users/create/", views.create_user, name="admin-create-user"),
    path("admin/users/<int:pk>/edit/", views.edit_user, name="admin-edit-user"),
    path("admin/users/<int:pk>/delete/", views.delete_user, name="admin-delete-user"),
    path("admin/users/<int:pk>/block/", views.block_user, name="admin-block-user"),
    path(
        "admin/users/<int:pk>/unblock/", views.unblock_user, name="admin-unblock-user"
    ),
    path(
        "admin/users/<int:pk>/promote/",
        views.promote_manager,
        name="admin-promote-manager",
    ),
    path("admin/users/<int:pk>/demote/", views.demote_user, name="admin-demote-user"),
    # Vehicle management (manager + admin access)
    # Admin
    path("admin/dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("admin/create/", views.create_user, name="create-user"),
    path("admin/<int:pk>/edit/", views.edit_user, name="edit-user"),
    path("admin/<int:pk>/delete/", views.delete_user, name="delete-user"),
    path("admin/<int:pk>/block/", views.block_user, name="block-user"),
    path("admin/<int:pk>/unblock/", views.unblock_user, name="unblock-user"),
    path("admin/<int:pk>/promote/", views.promote_manager, name="promote-manager"),
    path("admin/<int:pk>/demote/", views.demote_user, name="demote-user"),
    # Manager dashboards
    path("manager/dashboard/", views.manager_dashboard, name="manager-dashboard"),
    path("manager/vehicles/", views.manager_vehicles, name="manager-vehicles"),
    path("manager/reservations/", views.reservation_list, name="reservation-list"),
    # Vehicle management
    path("vehicles/", views.vehicle_list, name="vehicle-list"),
    path("vehicles/create/", views.vehicle_create, name="vehicle-create"),
    path("vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle-edit"),
    path("vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle-delete"),
    # Reservation management
    path("reservations/", views.reservation_list, name="reservation-list"),
    # Reservation group actions
    path(
        "reservations/group/<int:pk>/approve/",
        views.reservation_group_approve,
        name="reservation-group-approve",
    ),
    path(
        "reservations/group/<int:pk>/reject/",
        views.reservation_group_reject,
        name="reservation-group-reject",
    ),
    path(
        "reservations/group/<int:pk>/update/",
        views.reservation_update,
        name="reservation-update",
    ),
    # Single reservation actions
    path(
        "reservations/<int:pk>/approve/",
        views.reservation_approve,
        name="reservation-approve",
    ),
    path(
        "reservations/<int:pk>/reject/",
        views.reservation_reject,
        name="reservation-reject",
    ),
    path(
        "reservations/<int:pk>/cancel/",
        views.reservation_cancel,
        name="reservation-cancel",
    ),
    # User reservations
    path("my-reservations/", views.user_reservations, name="user-reservations"),
    # Locations
    path("locations/", views.location_list, name="location-list"),
    path("locations/create/", views.location_create, name="location-create"),
    path("locations/<int:pk>/edit/", views.location_edit, name="location-edit"),
    path("locations/<int:pk>/delete/", views.location_delete, name="location-delete"),
    # Admin dashboard + user management
    path("admin/dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("admin/users/create/", views.create_user, name="admin-create-user"),
    path("admin/users/<int:pk>/edit/", views.edit_user, name="admin-edit-user"),
    path("admin/users/<int:pk>/delete/", views.delete_user, name="admin-delete-user"),
    path("admin/users/<int:pk>/block/", views.block_user, name="admin-block-user"),
    path(
        "admin/users/<int:pk>/unblock/", views.unblock_user, name="admin-unblock-user"
    ),
    path(
        "admin/users/<int:pk>/promote/",
        views.promote_manager,
        name="admin-promote-manager",
    ),
    path("admin/users/<int:pk>/demote/", views.demote_user, name="admin-demote-user"),
    # Manager dashboards
    path("manager/dashboard/", views.manager_dashboard, name="manager-dashboard"),
    path("manager/vehicles/", views.vehicle_list, name="vehicle-list"),
    path("manager/vehicles/create/", views.vehicle_create, name="vehicle-create"),
    path("manager/vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle-edit"),
    path(
        "manager/vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle-delete"
    ),
    # Manager reservations (group-level + item-level)
    path("manager/reservations/", views.reservation_list, name="reservation-list"),
    path(
        "manager/reservations/<int:pk>/approve/",
        views.reservation_group_approve,
        name="reservation-group-approve",
    ),
    path(
        "manager/reservations/<int:pk>/reject/",
        views.reservation_group_reject,
        name="reservation-group-reject",
    ),
    path(
        "manager/reservations/<int:pk>/update/",
        views.reservation_update,
        name="reservation-update",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/approve/",
        views.reservation_approve,
        name="reservation-approve",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/reject/",
        views.reservation_reject,
        name="reservation-reject",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/cancel/",
        views.reservation_cancel,
        name="reservation-cancel",
    ),
    # Manager locations
    path("manager/locations/", views.location_list, name="location-list"),
    path("manager/locations/create/", views.location_create, name="location-create"),
    path("manager/locations/<int:pk>/edit/", views.location_edit, name="location-edit"),
    path(
        "manager/locations/<int:pk>/delete/",
        views.location_delete,
        name="location-delete",
    ),
    # User’s own reservations
    path("reservations/", views.user_reservations, name="user-reservations"),
    path(
        "reservations/<int:pk>/complete/",
        views.reservation_complete,
        name="reservation-complete",
    ),

]
