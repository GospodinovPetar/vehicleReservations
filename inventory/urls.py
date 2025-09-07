from django.urls import path
from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("reserve/", views.reserve, name="reserve"),
    path("reservations/", views.reservations, name="reservations"),
    path(
        "reservations/<int:pk>/reject/",
        views.reject_reservation,
        name="reject_reservation",
    ),
]
