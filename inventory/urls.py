from views.search import search, home
from views.reservations import reserve, reservations, reject_reservation
from django.urls import path


app_name = "inventory"

urlpatterns = [
    path("", home, name="home"),
    path("search/", search, name="search"),
    path("reserve/", reserve, name="reserve"),
    path("reservations/", reservations, name="reservations"),
    path(
        "reservations/<int:pk>/reject/",
        reject_reservation,
        name="reject_reservation",
    ),
]
