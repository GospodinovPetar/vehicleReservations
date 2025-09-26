from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import transaction

from .forms import CheckoutForm
from .models import PaymentIntent, PaymentIntentStatus
from inventory.models.reservation import ReservationStatus, VehicleReservation


def _brand(digits: str) -> str | None:
    if digits.startswith(("51", "52", "53", "54", "55")) or (
        digits[:2].isdigit() and 22 <= int(digits[:2]) <= 27
    ):
        return "mastercard"
    if digits.startswith("4"):
        return "visa"
    if digits.startswith(("34", "37")):
        return "amex"
    if digits.startswith(("60", "64", "65")):
        return "discover"
    return None


def _eur_amount(intent: PaymentIntent) -> str:
    """Represent integer cents as a human € string, e.g. 12345 -> '123.45'."""
    cents = int(intent.amount or 0)
    euros = cents // 100
    rem = cents % 100
    return f"{euros}.{rem:02d}"


def _cd(data, *keys, default=""):
    """Cleaned-data helper: return the first present key."""
    for k in keys:
        v = data.get(k)
        if v not in (None, ""):
            return v
    return default


@require_http_methods(["GET", "POST"])
def checkout_page(request, client_secret: str):
    """
    GET: render the card form.
    POST: process card -> success / fail / cancel. (No 3DS simulation.)
    """
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)

    if intent.is_expired():
        intent.status = PaymentIntentStatus.EXPIRED
        intent.save(update_fields=["status"])
        messages.error(request, "Payment session expired. Please try again.")
        return redirect("mockpay:result", client_secret=client_secret)

    if intent.status != PaymentIntentStatus.REQUIRES_CONFIRMATION:
        return redirect("mockpay:result", client_secret=client_secret)

    if request.method == "GET":
        form = CheckoutForm()
        return render(
            request,
            "mockpay/checkout.html",
            {"intent": intent, "form": form, "amount_eur": _eur_amount(intent)},
        )

    form = CheckoutForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "mockpay/checkout.html",
            {"intent": intent, "form": form, "amount_eur": _eur_amount(intent)},
            status=400,
        )

    pan: str = _cd(form.cleaned_data, "card_number", "cc_number").replace(" ", "")
    chosen = _cd(form.cleaned_data, "outcome", default="auto")

    if chosen == "auto":
        if pan == "4242424242424242":
            outcome = "success"
        elif pan == "4000000000000002":
            outcome = "fail"
        else:
            outcome = "success"
    else:
        outcome = chosen

    with transaction.atomic():
        intent.refresh_from_db()

        if outcome == "success":
            intent.status = PaymentIntentStatus.SUCCEEDED
            intent.save(update_fields=["status"])

            grp = intent.reservation_group
            grp.status = ReservationStatus.RESERVED
            grp.save(update_fields=["status"])

            messages.success(request, "Payment successful.")
            return redirect(
                "mockpay:checkout_success", client_secret=intent.client_secret
            )

        if outcome == "fail":
            intent.status = PaymentIntentStatus.FAILED
            intent.save(update_fields=["status"])
            messages.error(request, "Payment failed.")
        else:  # treat anything else as explicit cancel
            intent.status = PaymentIntentStatus.CANCELED
            intent.save(update_fields=["status"])
            messages.info(request, "Payment canceled.")

    return redirect("mockpay:result", client_secret=client_secret)


@require_http_methods(["GET"])
def checkout_success(request, client_secret: str):
    """Dedicated success page (separate from generic result)."""
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)
    return render(
        request,
        "mockpay/result.html",
        {"intent": intent, "amount_eur": _eur_amount(intent)},
    )


@require_http_methods(["GET"])
def result(request, client_secret: str):
    """Generic result page for failed/canceled/expired/other statuses."""
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)
    return render(
        request,
        "mockpay/result.html",
        {"intent": intent, "amount_eur": _eur_amount(intent)},
    )
