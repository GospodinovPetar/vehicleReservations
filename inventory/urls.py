from django.urls import path

from inventory.views.cart.add_to_cart import add_to_cart
from inventory.views.cart.checkout import checkout
from inventory.views.cart.remove_from_cart import remove_from_cart
from inventory.views.cart.view_cart import view_cart
from inventory.views.reservations.cancel_group import cancel_group
from inventory.views.reservations.delete_reservation import delete_reservation
from inventory.views.reservations.edit_reservation import edit_reservation
from inventory.views.reservations.my_reservations import my_reservations
from inventory.views.reservations.reject_reservation import reject_reservation
from inventory.views.search import home, search

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
    path(
        "reservations/<int:pk>/delete/", delete_reservation, name="delete_reservation"
    ),
]
