from __future__ import annotations

import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.db import transaction

from .forms import CheckoutForm
from .helpers import _to_cents, _eur_amount, _cd
from .models import PaymentIntent, PaymentIntentStatus
from inventory.models.reservation import ReservationStatus, ReservationGroup


@login_required
@transaction.atomic
def create_payment_intent(request: HttpRequest, group_id: int) -> HttpResponse:
    """
    Create a PaymentIntent for the user's reservation group currently awaiting payment.

    Rules:
        - Allowed only when group status is AWAITING_PAYMENT.
        - Amount is the sum of reservation item totals (converted to cents).
        - Fails if the computed amount is not positive.
        - Returns a redirect to the checkout page for this intent.

    Args:
        request: Django HttpRequest (authenticated user required).
        group_id: ReservationGroup primary key.

    Returns:
        HttpResponse: Redirect to the mock checkout page, or back to reservations with a message.
    """
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


@require_http_methods(["GET", "POST"])
def checkout_page(request: HttpRequest, client_secret: str) -> HttpResponse:
    """
    Display/process the mock checkout form for a PaymentIntent.

    GET:
        - If the intent is expired or not awaiting confirmation, redirect to result.
        - Otherwise render the form.

    POST:
        - Validate form and decide an outcome:
            * auto mode:
                - PAN 4242...4242  → success
                - PAN 4000...0002  → fail
                - otherwise         → success
            * explicit "success" / "fail" / "cancel"
        - Update PaymentIntent status accordingly.
        - On success, set the reservation group to RESERVED.
        - Redirect to a result page (or success page).

    Args:
        request: Django HttpRequest.
        client_secret: Token identifying the PaymentIntent.

    Returns:
        HttpResponse: Rendered form (GET/invalid POST) or a redirect to the result page.
    """
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
    """
    Display the success page for a completed (SUCCEEDED) PaymentIntent.

    Args:
        request: Django HttpRequest.
        client_secret: Token identifying the PaymentIntent.

    Returns:
        HttpResponse: Rendered success/result page.
    """
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)
    return render(
        request,
        "mockpay/result.html",
        {"intent": intent, "amount_eur": _eur_amount(intent)},
    )


@require_http_methods(["GET"])
def result(request: HttpRequest, client_secret: str) -> HttpResponse:
    """
    Display the result page for any PaymentIntent state.

    Args:
        request: Django HttpRequest.
        client_secret: Token identifying the PaymentIntent.

    Returns:
        HttpResponse: Rendered result page with human-readable amount.
    """
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)
    return render(
        request,
        "mockpay/result.html",
        {"intent": intent, "amount_eur": _eur_amount(intent)},
    )
