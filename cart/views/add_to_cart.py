from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from inventory.helpers.parse_iso_date import parse_iso_date
from cart.models.cart import Cart, CartItem
from inventory.models.reservation import Location
from inventory.models.vehicle import Vehicle


@login_required
@require_http_methods(["POST"])
def add_to_cart(request):
    vehicle = get_object_or_404(Vehicle, pk=request.POST.get("vehicle"))

    start_date = parse_iso_date(request.POST.get("start"))
    end_date = parse_iso_date(request.POST.get("end"))
    if not start_date or not end_date:
        messages.error(request, "Start and end dates are required.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    pickup = Location.objects.filter(pk=request.POST.get("pickup_location")).first()
    return_loc = Location.objects.filter(pk=request.POST.get("return_location")).first()

    cart = Cart.get_or_create_active(request.user)
    item = CartItem(
        cart=cart,
        vehicle=vehicle,
        start_date=start_date,
        end_date=end_date,
        pickup_location=pickup,
        return_location=return_loc,
    )

    try:
        item.full_clean()

        merged = CartItem.merge_or_create(
            cart=cart,
            vehicle=vehicle,
            start_date=start_date,
            end_date=end_date,
            pickup_location=pickup,
            return_location=return_loc,
        )

        messages.success(
            request,
            f"Added {vehicle} to cart. Period now {merged.start_date} → {merged.end_date}."
        )
        return redirect("cart:view_cart")

    except ValidationError as ve:
        msg = "; ".join(getattr(ve, "messages", []) or [str(ve)])
        messages.error(request, msg or "Could not add this item to your cart.")
        return redirect(request.META.get("HTTP_REFERER", "/"))
