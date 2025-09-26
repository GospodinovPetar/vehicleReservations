from django.urls import path
from . import views

app_name = "manager"

urlpatterns = [
    path("", views.manager_dashboard, name="dashboard"),
    # Vehicles
    path("vehicles/", views.manager_vehicles, name="vehicles"),
    path("vehicles/add/", views.vehicle_create, name="vehicle-create"),
    path("vehicles/<int:pk>/edit/", views.vehicle_edit, name="vehicle-edit"),
    path("vehicles/<int:pk>/delete/", views.vehicle_delete, name="vehicle-delete"),
    # Reservations
    path("reservations/", views.manager_reservations, name="reservations"),
    path("reservations/", views.reservation_list, name="reservation-list"),
    path(
        "reservations/<int:pk>/update/",
        views.reservation_update,
        name="reservation-update",
    ),
    path(
        "reservations/group/<int:pk>/complete/",
        views.reservation_group_complete,
        name="reservation-group-complete",
    ),
]
