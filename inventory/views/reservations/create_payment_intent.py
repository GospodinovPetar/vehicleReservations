from __future__ import annotations

import secrets
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect

from inventory.models.reservation import ReservationGroup, ReservationStatus
from mockpay.models import PaymentIntent, PaymentIntentStatus


def _q2(value: Optional[Decimal]) -> Decimal:
    if value is None:
        value = Decimal("0")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_cents(value: Optional[Decimal]) -> int:
    quantized = _q2(value or Decimal("0"))
    cents = (quantized * 100).to_integral_value(rounding=ROUND_HALF_UP)
    return int(cents)


@login_required
@transaction.atomic
def create_payment_intent(request: HttpRequest, group_id: int) -> HttpResponse:
    group = get_object_or_404(
        ReservationGroup.objects.select_for_update(),
        pk=group_id,
        user=request.user,
    )

    if group.status != ReservationStatus.AWAITING_PAYMENT:
        messages.error(request, "This reservation is not awaiting payment.")
        return redirect("inventory:reservations")

    amount_cents_total = 0
    items = group.reservations.select_related("vehicle").all()
    for item in items:
        item_total = getattr(item, "total_price", None)
        amount_cents_total += _to_cents(item_total)

    if amount_cents_total <= 0:
        messages.error(request, "Invalid amount to pay.")
        return redirect("inventory:reservations")

    client_secret_value = secrets.token_hex(24)

    intent = PaymentIntent.objects.create(
        reservation_group=group,
        amount=amount_cents_total,
        currency="EUR",
        client_secret=client_secret_value,
        status=PaymentIntentStatus.REQUIRES_CONFIRMATION,
    )

    return redirect("mockpay:checkout_page", client_secret=intent.client_secret)
