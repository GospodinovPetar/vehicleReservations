from __future__ import annotations

from typing import Optional

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.db import transaction

from .forms import CheckoutForm
from .models import PaymentIntent, PaymentIntentStatus
from inventory.models.reservation import ReservationStatus


def _eur_amount(intent: PaymentIntent) -> str:
    cents_value = int(getattr(intent, "amount", 0) or 0)
    euros_part = cents_value // 100
    cents_part = cents_value % 100
    return f"{euros_part}.{cents_part:02d}"


def _cd(data: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


@require_http_methods(["GET", "POST"])
def checkout_page(request: HttpRequest, client_secret: str) -> HttpResponse:
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)

    if intent.is_expired():
        if intent.status != PaymentIntentStatus.EXPIRED:
            intent.status = PaymentIntentStatus.EXPIRED
            intent.save(update_fields=["status"])
        messages.error(request, "Payment session expired. Please try again.")
        return redirect("mockpay:result", client_secret=client_secret)

    if request.method == "GET":
        if intent.status != PaymentIntentStatus.REQUIRES_CONFIRMATION:
            return redirect("mockpay:result", client_secret=client_secret)
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

    pan = _cd(form.cleaned_data, "card_number", "cc_number").replace(" ", "")
    chosen_outcome = _cd(form.cleaned_data, "outcome", default="auto")

    if chosen_outcome == "auto":
        if pan == "4242424242424242":
            outcome = "success"
        elif pan == "4000000000000002":
            outcome = "fail"
        else:
            outcome = "success"
    else:
        outcome = chosen_outcome

    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .select_related("reservation_group")
            .get(pk=intent.pk)
        )

        if intent.status != PaymentIntentStatus.REQUIRES_CONFIRMATION:
            return redirect("mockpay:result", client_secret=client_secret)

        if intent.is_expired():
            intent.status = PaymentIntentStatus.EXPIRED
            intent.save(update_fields=["status"])
            messages.error(request, "Payment session expired. Please try again.")
            return redirect("mockpay:result", client_secret=client_secret)

        grp = intent.reservation_group

        payable_states = {ReservationStatus.PENDING, ReservationStatus.AWAITING_PAYMENT}
        if grp.status not in payable_states:
            messages.error(request, "This reservation is no longer payable.")
            return redirect("mockpay:result", client_secret=client_secret)

        has_lines = grp.reservations.exists()
        if not has_lines:
            messages.error(request, "Your reservation items are no longer available.")
            return redirect("mockpay:result", client_secret=client_secret)

        if outcome == "success":
            intent.status = PaymentIntentStatus.SUCCEEDED
            intent.save(update_fields=["status"])
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
        else:
            intent.status = PaymentIntentStatus.CANCELED
            intent.save(update_fields=["status"])
            messages.info(request, "Payment canceled.")

    return redirect("mockpay:result", client_secret=client_secret)


@require_http_methods(["GET"])
def checkout_success(request: HttpRequest, client_secret: str) -> HttpResponse:
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)
    return render(
        request,
        "mockpay/result.html",
        {"intent": intent, "amount_eur": _eur_amount(intent)},
    )


@require_http_methods(["GET"])
def result(request: HttpRequest, client_secret: str) -> HttpResponse:
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)
    return render(
        request,
        "mockpay/result.html",
        {"intent": intent, "amount_eur": _eur_amount(intent)},
    )
