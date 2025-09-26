import secrets
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect

from inventory.models.reservation import ReservationGroup, ReservationStatus
from mockpay.models import PaymentIntent, PaymentIntentStatus


def _q2(dec: Decimal) -> Decimal:
    return (dec or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_cents(dec: Decimal) -> int:
    return int((_q2(dec) * 100).to_integral_value(rounding=ROUND_HALF_UP))


@login_required
@transaction.atomic
def create_payment_intent(request, group_id: int):
    group = get_object_or_404(
        ReservationGroup.objects.select_for_update(), pk=group_id, user=request.user
    )

    if group.status != ReservationStatus.AWAITING_PAYMENT:
        messages.error(request, "This reservation is not awaiting payment.")
        return redirect("inventory:reservations")

    amount_cents = 0
    items = group.reservations.select_related("vehicle").all()
    for r in items:
        amount_cents += _to_cents(r.total_price or Decimal("0"))

    if amount_cents <= 0:
        messages.error(request, "Invalid amount to pay.")
        return redirect("inventory:reservations")

    client_secret = secrets.token_hex(24)
    intent = PaymentIntent.objects.create(
        reservation_group=group,
        amount=amount_cents,
        currency="EUR",
        client_secret=client_secret,
        status=PaymentIntentStatus.REQUIRES_CONFIRMATION,
    )

    return redirect("mockpay:checkout_page", client_secret=intent.client_secret)
