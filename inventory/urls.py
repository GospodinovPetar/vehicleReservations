from django.urls import path

from inventory.views.search import home, search
from inventory.views.reservations import (
    reject_reservation,
    my_reservations,
    cancel_group,
    edit_reservation,
    delete_reservation,
)
from inventory.views.cart import (
    add_to_cart,
    view_cart,
    remove_from_cart,
    checkout,
)

app_name = "inventory"

urlpatterns = [
    path("", home, name="home"),
    path("search/", search, name="search"),
    path("reserve/", add_to_cart, name="reserve"),
    path("cart/", view_cart, name="view_cart"),
    path("cart/remove/<int:item_id>/", remove_from_cart, name="remove_from_cart"),
    path("cart/checkout/", checkout, name="checkout"),
    path("reservations/", my_reservations, name="reservations"),
    path(
        "reservations/<int:pk>/reject/", reject_reservation, name="reject_reservation"
    ),
    path(
        "reservations/group/<int:group_id>/cancel/", cancel_group, name="cancel_group"
    ),
    path("reservations/<int:pk>/edit/", edit_reservation, name="edit_reservation"),
    path("reservations/<int:pk>/delete/", delete_reservation, name="delete_reservation"),
]
