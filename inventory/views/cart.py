from decimal import Decimal
import secrets


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.pricing import RateTable, quote_total
from inventory.models.cart import Cart, CartItem, ReservationGroup
from inventory.models.reservation import Location, Reservation, ReservationStatus
from inventory.models.vehicle import Vehicle


@login_required
def view_cart(request):
    cart = Cart.get_or_create_active(request.user)
    items = list(
        CartItem.objects.filter(cart=cart).select_related(
            "vehicle", "pickup_location", "return_location"
        )
    )

    rows = []
    for it in items:
        q = quote_total(
            it.start_date,
            it.end_date,
            RateTable(day=float(it.vehicle.price_per_day), currency="EUR"),
        )
        rows.append({"item": it, "days": q["days"], "total": Decimal(str(q["total"]))})

    return render(request, "inventory/cart.html", {"cart": cart, "rows": rows})


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
        item.save()
    except Exception as e:
        messages.error(request, f"Could not add to cart: {e}")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    messages.success(request, f"Added {vehicle} to cart.")
    return redirect("inventory:view_cart")


@login_required
@require_http_methods(["POST"])
def remove_from_cart(request, item_id):
    cart = Cart.get_or_create_active(request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.success(request, "Removed item from cart.")
    return redirect("inventory:view_cart")


@login_required
@require_http_methods(["POST"])
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user, is_checked_out=False)

    items = list(
        CartItem.objects.filter(cart=cart)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("start_date", "vehicle_id")
    )
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("inventory:view_cart")

    with transaction.atomic():
        vehicle_ids = sorted({it.vehicle_id for it in items})
        list(
            Vehicle.objects.select_for_update()
            .filter(id__in=vehicle_ids)
            .order_by("id")
        )

        for it in items:
            if not Reservation.is_vehicle_available(
                vehicle=it.vehicle,
                start_date=it.start_date,
                end_date=it.end_date,
                pickup=it.pickup_location,
                ret=it.return_location,
            ):
                messages.error(
                    request,
                    f"{it.vehicle} is no longer available for {it.start_date} → {it.end_date}.",
                )
                return redirect("inventory:view_cart")

        group = ReservationGroup.objects.create(user=request.user)
        if not getattr(group, "reference", None):
            group.reference = secrets.token_hex(4).upper()
            group.save(update_fields=["reference"])

        for it in items:
            Reservation.objects.create(
                user=request.user,
                vehicle=it.vehicle,
                pickup_location=it.pickup_location,
                return_location=it.return_location,
                start_date=it.start_date,
                end_date=it.end_date,
                status=ReservationStatus.RESERVED,
                group=group,
            )

        cart.is_checked_out = True
        cart.save(update_fields=["is_checked_out"])
        CartItem.objects.filter(cart=cart).delete()

    messages.success(request, f"Reservation confirmed. Reference: {group.reference}.")
    return redirect("inventory:reservations")
