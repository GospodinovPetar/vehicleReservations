from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from cart.models.cart import Cart, CartItem

@login_required
@require_http_methods(["POST"])
def remove_from_cart(request, item_id):
    cart = Cart.get_or_create_active(request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.success(request, "Removed item from views.")
    return redirect("inventory:view_cart")