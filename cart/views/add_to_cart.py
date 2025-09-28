from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from inventory.helpers.parse_iso_date import parse_iso_date
from cart.models.cart import Cart, CartItem
from inventory.models.reservation import Location
from inventory.models.vehicle import Vehicle


@login_required
@require_http_methods(["POST"])
@csrf_protect
def add_to_cart(request: HttpRequest) -> HttpResponse:
    referer_url = request.META.get("HTTP_REFERER", "/")

    vehicle_param = request.POST.get("vehicle")
    start_param = request.POST.get("start")
    end_param = request.POST.get("end")
    pickup_param = request.POST.get("pickup_location")
    return_param = request.POST.get("return_location")

    vehicle_obj = get_object_or_404(Vehicle, pk=vehicle_param)

    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None:
        messages.error(request, "Start and end dates are required.")
        return redirect(referer_url)

    if (
        pickup_param is None
        or pickup_param == ""
        or return_param is None
        or return_param == ""
    ):
        messages.error(request, "Please select both pickup and return locations.")
        return redirect(referer_url)

    pickup_obj = Location.objects.filter(pk=pickup_param).first()
    return_obj = Location.objects.filter(pk=return_param).first()
    if pickup_obj is None or return_obj is None:
        messages.error(request, "Selected pickup/return location was not found.")
        return redirect(referer_url)

    cart_obj = Cart.get_or_create_active(request.user)

    item = CartItem(
        cart=cart_obj,
        vehicle=vehicle_obj,
        start_date=start_date,
        end_date=end_date,
        pickup_location=pickup_obj,
        return_location=return_obj,
    )

    try:
        item.full_clean()

        merged_item = CartItem.merge_or_create(
            cart=cart_obj,
            vehicle=vehicle_obj,
            start_date=start_date,
            end_date=end_date,
            pickup_location=pickup_obj,
            return_location=return_obj,
        )

        vehicle_str = str(vehicle_obj)
        period_str = f"{merged_item.start_date} \u2192 {merged_item.end_date}"
        messages.success(
            request, f"Added {vehicle_str} to cart. Period now {period_str}."
        )
        return redirect("cart:view_cart")

    except ValidationError as exc:
        message_list = getattr(exc, "messages", None)
        if not message_list:
            error_msg = str(exc)
        else:
            error_msg = "; ".join(message_list)
        if not error_msg:
            error_msg = "Could not add this item to your cart."
        messages.error(request, error_msg)
        return redirect(referer_url)
