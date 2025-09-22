from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

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
    path("vehicles/", views.vehicle_list, name="vehicle-list"),
    path("vehicles/create/", views.vehicle_create, name="vehicle-create"),
    path("vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle-edit"),
    path("vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle-delete"),

    # Reservation management
    path("reservations/", views.reservation_list, name="reservation-list"),
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
        "reservations/<int:pk>/update/",
        views.reservation_update,
        name="reservation-update",
    ),

    # User's own reservations
    path("reservations/", views.user_reservations, name="user-reservations"),

    # Manager convenience routes (if you want a separate manager namespace)
    path(
        "manager/reservations/", views.manager_reservations, name="manager-reservations"
    ),

    # Locations management (manager + admin)
    path("locations/", views.location_list, name="location-list"),
    path("locations/create/", views.location_create, name="location-create"),
    path("locations/<int:pk>/edit/", views.location_edit, name="location-edit"),
    path("locations/<int:pk>/delete/", views.location_delete, name="location-delete"),
]
