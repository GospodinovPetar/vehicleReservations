from django.urls import path

from cart.views.add_to_cart import add_to_cart
from cart.views.checkout import checkout
from cart.views.remove_from_cart import remove_from_cart
from cart.views.view_cart import view_cart
from inventory.views.payment_intent import create_payment_intent
from inventory.views.reservation_actions import my_reservations, reject_reservation, cancel_reservation, add_vehicle, \
    edit_reservation, delete_reservation, approve_group
from inventory.views.search import search, home

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
        "reservations/group/<int:group_id>/cancel/",
        cancel_reservation,
        name="cancel_group",
    ),
    path("reservations/group/<int:group_id>/add/", add_vehicle, name="add_vehicle"),
    path("reservations/<int:pk>/edit/", edit_reservation, name="edit_reservation"),
    path(
        "reservations/<int:pk>/delete/", delete_reservation, name="delete_reservation"
    ),
    path(
        "reservations/group/<int:group_id>/approve/",
        approve_group,
        name="approve_group",
    ),
    path(
        "reservations/group/<int:group_id>/pay/",
        create_payment_intent,
        name="create_payment_intent",
    ),
]
