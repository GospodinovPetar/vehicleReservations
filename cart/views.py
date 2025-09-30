from __future__ import annotations

import secrets
from django.db import transaction
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from inventory.helpers.parse_iso_date import parse_iso_date
from cart.models.cart import Cart, CartItem
from inventory.helpers.pricing import quote_total, RateTable
from inventory.models.reservation import Location, ReservationStatus, ReservationGroup, VehicleReservation
from inventory.models.vehicle import Vehicle

@login_required
@require_http_methods(["POST"])
@csrf_protect
def add_to_cart(request: HttpRequest) -> HttpResponse:
    """
    Add a vehicle reservation candidate to the user’s active cart.

    Behavior:
        - Validates presence and parsability of start/end dates.
        - Ensures both pickup and return locations exist.
        - Runs model validation on a prospective CartItem.
        - Merges with a compatible existing CartItem or creates a new one.
        - On success, redirects to the cart; on error, returns to the referrer.

    POST parameters:
        vehicle: Vehicle primary key.
        start: ISO date string (YYYY-MM-DD).
        end: ISO date string (YYYY-MM-DD).
        pickup_location: Location primary key.
        return_location: Location primary key.

    Returns:
        HttpResponse: Redirect to cart on success, or back to the referring page on error.
    """
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


def _quantize_money(value: Decimal) -> Decimal:
    """
    Quantize a Decimal monetary value to two decimal places with ROUND_HALF_UP.

    Args:
        value (Decimal): The amount to quantize. If None, treated as 0.

    Returns:
        Decimal: The quantized amount with exactly two fractional digits.
    """
    if value is None:
        value = Decimal("0")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cents(value: Decimal) -> int:
    """
    Convert a Decimal money amount to integer cents using two-decimal quantization.

    Args:
        value (Decimal): Monetary amount (e.g., 12.34).

    Returns:
        int: Amount in cents (e.g., 1234).
    """
    amount = _quantize_money(value or Decimal("0"))
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


@login_required
@require_http_methods(["POST"])
def checkout(request: HttpRequest) -> HttpResponse:
    """
    Convert the current cart into reservations under a (re)usable pending group.

    Steps:
        - Lock the active cart and its vehicles for update to avoid race conditions.
        - Validate there are items and no availability conflicts.
        - Reuse an existing PENDING/AWAITING_PAYMENT ReservationGroup for the user
          or create a new one and ensure it has a unique short reference.
        - Create VehicleReservation rows for each cart item.
        - Mark the cart as checked out and clear its items.
        - Compute quotes per reservation, persist per-reservation totals, and
          accumulate the overall amount (in cents) for potential payment usage.
        - Inform the user and redirect to the reservations page.

    Returns:
        HttpResponse: Redirect to the cart on error, or to the reservations page on success.
    """
    with transaction.atomic():
        cart_obj: Optional[Cart] = (
            Cart.objects.select_for_update()
            .select_related("user")
            .filter(user=request.user, is_checked_out=False)
            .first()
        )
        if cart_obj is None:
            messages.info(request, "Your cart is empty or already checked out.")
            return redirect("cart:view_cart")

        cart_items: List[CartItem] = list(
            CartItem.objects.filter(cart=cart_obj)
            .select_related("vehicle", "pickup_location", "return_location")
            .order_by("start_date", "vehicle_id")
        )
        if len(cart_items) == 0:
            messages.info(request, "Your cart is empty.")
            return redirect("cart:view_cart")

        vehicle_ids = sorted({item.vehicle_id for item in cart_items})
        list(
            Vehicle.objects.select_for_update()
            .filter(id__in=vehicle_ids)
            .order_by("id")
        )

        for item in cart_items:
            conflict_exists = VehicleReservation.objects.filter(
                vehicle=item.vehicle,
                group__status__in=ReservationStatus.blocking(),
                start_date__lt=item.end_date,
                end_date__gt=item.start_date,
            ).exists()
            if conflict_exists:
                vehicle_str = str(item.vehicle)
                period_str = f"{item.start_date} \u2192 {item.end_date}"
                messages.error(
                    request, f"{vehicle_str} is no longer available for {period_str}."
                )
                return redirect("cart:view_cart")

        existing_group = (
            ReservationGroup.objects.select_for_update()
            .filter(
                user=request.user,
                status__in=[
                    ReservationStatus.PENDING,
                    ReservationStatus.AWAITING_PAYMENT,
                ],
            )
            .order_by("-created_at")
            .first()
        )
        if existing_group is None:
            group_obj = ReservationGroup.objects.create(
                user=request.user, status=ReservationStatus.PENDING
            )
        else:
            group_obj = existing_group

        if not getattr(group_obj, "reference", None):
            attempts_remaining = 5
            while attempts_remaining > 0:
                candidate = secrets.token_hex(4).upper()
                already_exists = ReservationGroup.objects.filter(
                    reference=candidate
                ).exists()
                if not already_exists:
                    group_obj.reference = candidate
                    group_obj.save(update_fields=["reference"])
                    break
                attempts_remaining -= 1

        for item in cart_items:
            VehicleReservation.objects.create(
                user=request.user,
                vehicle=item.vehicle,
                pickup_location=item.pickup_location,
                return_location=item.return_location,
                start_date=item.start_date,
                end_date=item.end_date,
                group=group_obj,
            )

        cart_obj.is_checked_out = True
        cart_obj.save(update_fields=["is_checked_out"])
        CartItem.objects.filter(cart=cart_obj).delete()

    total_amount_cents = 0
    reservations_qs = group_obj.reservations.select_related("vehicle").all()

    for reservation in reservations_qs:
        vehicle_day_rate = Decimal(
            str(getattr(reservation.vehicle, "price_per_day", "0"))
        )
        rate_table = RateTable(day=float(vehicle_day_rate), currency="EUR")
        quote_info = quote_total(
            reservation.start_date, reservation.end_date, rate_table
        )

        total_decimal = Decimal(str(quote_info.get("total", "0")))
        total_decimal = _quantize_money(total_decimal)

        reservation.total_price = total_decimal
        reservation.save(update_fields=["total_price"])

        total_amount_cents += _cents(total_decimal)

    messages.success(
        request, f"Reservation submitted. Ref: {group_obj.reference} (status: Pending)"
    )
    return redirect("inventory:reservations")


@login_required
@require_http_methods(["POST"])
def remove_from_cart(request, item_id):
    """
    Remove a specific item from the user’s active cart.

    Args:
        item_id (int): Primary key of the CartItem to remove.

    Returns:
        HttpResponse: Redirect back to the cart view after deletion.
    """
    cart = Cart.get_or_create_active(request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.success(request, "Removed item from views.")
    return redirect("inventory:view_cart")


@login_required
def view_cart(request: HttpRequest) -> HttpResponse:
    """
    Display the current user’s active cart with per-item quote details.

    Context:
        cart (Cart): The active cart for the user (created if missing).
        rows (list[dict]): One entry per CartItem with:
            - item (CartItem)
            - days (int): Number of rental days per item.
            - total (Decimal): Computed total price for the item.
        cart_total (Decimal): Sum of item totals.

    Returns:
        HttpResponse: Rendered cart page.
    """
    cart_obj: Cart = Cart.get_or_create_active(request.user)

    items_qs = CartItem.objects.filter(cart=cart_obj).select_related(
        "vehicle",
        "pickup_location",
        "return_location",
    )
    items: List[CartItem] = list(items_qs)

    rows: List[Dict[str, Any]] = []
    for item in items:
        vehicle_obj = getattr(item, "vehicle", None)
        day_rate_float = 0.0
        if vehicle_obj is not None:
            price_attr = getattr(vehicle_obj, "price_per_day", 0)
            day_rate_float = float(price_attr or 0)

        rate_table = RateTable(day=day_rate_float, currency="EUR")
        quote = quote_total(item.start_date, item.end_date, rate_table)

        days_value = int(quote.get("days", 0))
        total_value = Decimal(str(quote.get("total", "0")))

        rows.append(
            {
                "item": item,
                "days": days_value,
                "total": total_value,
            }
        )

    cart_total: Decimal = sum((row["total"] for row in rows), Decimal("0"))

    context: Dict[str, Any] = {
        "cart": cart_obj,
        "rows": rows,
        "cart_total": cart_total,
    }
    return render(request, "cart/cart.html", context)
