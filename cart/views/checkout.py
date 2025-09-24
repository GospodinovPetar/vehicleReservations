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
from mockpay.models import PaymentIntent, PaymentIntentStatus


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
            if not VehicleReservation.is_vehicle_available(
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
                return redirect("cart:view_cart")

        # Create a fresh group
        group = ReservationGroup.objects.create(user=request.user)

        # Ensure a unique short reference (rarely collides, but let’s be safe)
        if not getattr(group, "reference", None):
            for _ in range(5):  # tiny loop; collisions are extremely unlikely
                ref = secrets.token_hex(4).upper()
                exists = ReservationGroup.objects.filter(reference=ref).exists()
                if not exists:
                    group.reference = ref
                    group.save(update_fields=["reference"])
                    break

        # Create the individual reservations in PENDING
        for it in items:
            VehicleReservation.objects.create(
                user=request.user,
                vehicle=it.vehicle,
                pickup_location=it.pickup_location,
                return_location=it.return_location,
                start_date=it.start_date,
                end_date=it.end_date,
                status=ReservationStatus.PENDING,
                group=group,
            )

        # Mark the cart as checked out & clear items (still inside the lock)
        cart.is_checked_out = True
        cart.save(update_fields=["is_checked_out"])
        CartItem.objects.filter(cart=cart).delete()

    amount_cents = 0
    reservations = group.reservations.select_related("vehicle").all()

    for r in reservations:
        # Use Decimal all the way
        day_rate = Decimal(str(r.vehicle.price_per_day))  # ensure Decimal
        rt = RateTable(day=float(day_rate), currency="EUR")  # RateTable expects float; OK for input
        q = quote_total(r.start_date, r.end_date, rt)

        # q["total"] may be float or str; coerce to Decimal safely
        total_dec = Decimal(str(q["total"]))
        total_dec = _quantize_money(total_dec)

        r.total_price = total_dec  # if the model is DecimalField, this is perfect
        r.save(update_fields=["total_price"])

        amount_cents += _cents(total_dec)

    # Create a PaymentIntent and send the user to the hosted mock checkout
    client_secret = secrets.token_hex(24)
    intent = PaymentIntent.objects.create(
        reservation_group=group,
        amount=amount_cents,
        currency="EUR",
        client_secret=client_secret,
        status=PaymentIntentStatus.REQUIRES_CONFIRMATION,
    )

    messages.info(request, f"Reference {group.reference}: proceed to payment.")
    return redirect("mockpay:checkout_page", client_secret=intent.client_secret)
