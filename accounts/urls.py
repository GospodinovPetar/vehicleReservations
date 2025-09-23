from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

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
    path("manager/reservations/", views.manager_reservations, name="manager-reservations"),

    # Vehicle management
    path("vehicles/", views.vehicle_list, name="vehicle-list"),
    path("vehicles/create/", views.vehicle_create, name="vehicle-create"),
    path("vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle-edit"),
    path("vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle-delete"),

    # Reservation management
    path("reservations/", views.reservation_list, name="reservation-list"),

    # Reservation group actions
    path("reservations/group/<int:pk>/approve/", views.reservation_group_approve, name="reservation-group-approve"),
    path("reservations/group/<int:pk>/reject/", views.reservation_group_reject, name="reservation-group-reject"),
    path("reservations/group/<int:pk>/update/", views.reservation_update, name="reservation-update"),

    # Single reservation actions
    path("reservations/<int:pk>/approve/", views.reservation_approve, name="reservation-approve"),
    path("reservations/<int:pk>/reject/", views.reservation_reject, name="reservation-reject"),
    path("reservations/<int:pk>/cancel/", views.reservation_cancel, name="reservation-cancel"),

    # User reservations
    path("my-reservations/", views.user_reservations, name="user-reservations"),

    # Locations
    path("locations/", views.location_list, name="location-list"),
    path("locations/create/", views.location_create, name="location-create"),
    path("locations/<int:pk>/edit/", views.location_edit, name="location-edit"),
    path("locations/<int:pk>/delete/", views.location_delete, name="location-delete"),
]
