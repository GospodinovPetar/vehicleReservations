from __future__ import annotations

import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from inventory.helpers.pricing import RateTable, quote_total
from cart.models.cart import Cart, CartItem
from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    ReservationGroup,
)
from inventory.models.vehicle import Vehicle


def _quantize_money(value: Decimal) -> Decimal:
    if value is None:
        value = Decimal("0")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cents(value: Decimal) -> int:
    amount = _quantize_money(value or Decimal("0"))
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


@login_required
@require_http_methods(["POST"])
def checkout(request: HttpRequest) -> HttpResponse:
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
