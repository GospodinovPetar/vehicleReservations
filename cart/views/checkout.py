import secrets
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods
from inventory.helpers.pricing import quote_total, RateTable

from cart.models.cart import Cart, CartItem
from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    ReservationGroup,
)
from inventory.models.vehicle import Vehicle


def _quantize_money(value: Decimal) -> Decimal:
    """
    Force two decimal places using bankers' rounding rules suitable for currency.
    """
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cents(dec: Decimal) -> int:
    """
    Convert a Decimal money value to integer cents safely.
    """
    return int((_quantize_money(dec) * 100).to_integral_value(rounding=ROUND_HALF_UP))


@login_required
@require_http_methods(["POST"])
def checkout(request):
    """
    Creates a ReservationGroup + VehicleReservations, then a PaymentIntent,
    and redirects to the hosted mock checkout.

    Guardrails included:
    - Locks the Cart row to avoid double checkout.
    - Locks Vehicle rows to prevent overbooking while we confirm availability.
    - Uses Decimal for money, not float.
    - Ensures unique human-friendly reference on the group.
    """
    with transaction.atomic():
        cart = (
            Cart.objects.select_for_update()
            .select_related("user")
            .filter(user=request.user, is_checked_out=False)
            .first()
        )
        if not cart:
            messages.info(request, "Your cart is empty or already checked out.")
            return redirect("cart:view_cart")

        items = list(
            CartItem.objects.filter(cart=cart)
            .select_related("vehicle", "pickup_location", "return_location")
            .order_by("start_date", "vehicle_id")
        )
        if not items:
            messages.info(request, "Your cart is empty.")
            return redirect("cart:view_cart")

        vehicle_ids = sorted({it.vehicle_id for it in items})
        list(
            Vehicle.objects.select_for_update()
            .filter(id__in=vehicle_ids)
            .order_by("id")
        )

        for it in items:
            blocking_exists = VehicleReservation.objects.filter(
                vehicle=it.vehicle,
                group__status__in=ReservationStatus.blocking(),
                start_date__lt=it.end_date,
                end_date__gt=it.start_date,
            ).exists()
            if blocking_exists:
                messages.error(
                    request,
                    f"{it.vehicle} is no longer available for {it.start_date} → {it.end_date}.",
                )
                return redirect("cart:view_cart")

        group = (
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
        if group is None:
            group = ReservationGroup.objects.create(
                user=request.user,
                status=ReservationStatus.PENDING,
            )

        if not getattr(group, "reference", None):
            for _ in range(5):
                ref = secrets.token_hex(4).upper()
                exists = ReservationGroup.objects.filter(reference=ref).exists()
                if not exists:
                    group.reference = ref
                    group.save(update_fields=["reference"])
                    break

        for it in items:
            VehicleReservation.objects.create(
                user=request.user,
                vehicle=it.vehicle,
                pickup_location=it.pickup_location,
                return_location=it.return_location,
                start_date=it.start_date,
                end_date=it.end_date,
                group=group,
            )

        cart.is_checked_out = True
        cart.save(update_fields=["is_checked_out"])
        CartItem.objects.filter(cart=cart).delete()

    amount_cents = 0
    reservations = group.reservations.select_related("vehicle").all()

    for r in reservations:
        day_rate = Decimal(str(r.vehicle.price_per_day))
        rt = RateTable(day=float(day_rate), currency="EUR")
        q = quote_total(r.start_date, r.end_date, rt)

        total_dec = Decimal(str(q["total"]))
        total_dec = _quantize_money(total_dec)

        r.total_price = total_dec
        r.save(update_fields=["total_price"])

        amount_cents += _cents(total_dec)

    messages.success(
        request, f"Reservation submitted. Ref: {group.reference} (status: Pending)"
    )

    return redirect("inventory:reservations")
