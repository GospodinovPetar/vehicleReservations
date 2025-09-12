from django.urls import path

from inventory.views.search import home, search
from inventory.views.reservations import reservations, reject_reservation
from inventory.views.cart import add_to_cart, view_cart, remove_from_cart, checkout, my_reservations, cancel_group

app_name = "inventory"

urlpatterns = [
    path("", home, name="home"),
    path("search/", search, name="search"),

    path("reserve/", add_to_cart, name="reserve"),
    path("cart/", view_cart, name="view_cart"),
    path("cart/remove/<int:item_id>/", remove_from_cart, name="remove_from_cart"),
    path("cart/checkout/", checkout, name="checkout"),

    path("reservations/", my_reservations, name="reservations"),
    path("reservations/<int:pk>/reject/", reject_reservation, name="reject_reservation"),
    path("reservations/group/<int:group_id>/cancel/", cancel_group, name="cancel_group"),
]
