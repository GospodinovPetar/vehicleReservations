from django.urls import path
from cart.views.view_cart import view_cart
from cart.views.add_to_cart import add_to_cart
from cart.views.remove_from_cart import remove_from_cart
from cart.views.checkout import checkout

app_name = "cart"

urlpatterns = [
    path("", view_cart, name="view_cart"),
    path("add/<int:vehicle_id>/", add_to_cart, name="add_to_cart"),
    path("remove/<int:item_id>/", remove_from_cart, name="remove_from_cart"),
    path("checkout/", checkout, name="checkout"),
]
