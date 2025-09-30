from django.urls import path

from cart.views import view_cart, add_to_cart, remove_from_cart, checkout

app_name = "cart"

urlpatterns = [
    path("", view_cart, name="view_cart"),
    path("add/<int:vehicle_id>/", add_to_cart, name="add_to_cart"),
    path("remove/<int:item_id>/", remove_from_cart, name="remove_from_cart"),
    path("checkout/", checkout, name="checkout"),
]
