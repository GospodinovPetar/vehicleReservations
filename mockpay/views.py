from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import transaction

from .forms import CheckoutForm
from .models import PaymentIntent, PaymentIntentStatus
from inventory.models.reservation import ReservationStatus

def _brand(digits: str) -> str | None:
    if digits.startswith(("51","52","53","54","55")) or (digits[:2].isdigit() and 22 <= int(digits[:2]) <= 27):
        return "mastercard"
    if digits.startswith("4"):
        return "visa"
    if digits.startswith(("34","37")):
        return "amex"
    if digits.startswith(("60","64","65")):
        return "discover"
    return None

@require_http_methods(["GET", "POST"])
def checkout_page(request, client_secret: str):
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)

    if intent.is_expired():
        intent.status = PaymentIntentStatus.EXPIRED
        intent.save(update_fields=["status"])
        messages.error(request, "Payment session expired. Please try again.")
        return redirect("mockpay:result", client_secret=client_secret)

    if intent.status not in (PaymentIntentStatus.REQUIRES_CONFIRMATION, PaymentIntentStatus.PROCESSING):
        return redirect("mockpay:result", client_secret=client_secret)

    if request.method == "GET":
        form = CheckoutForm()
        return render(request, "mockpay/checkout.html", {"intent": intent, "form": form})

    form = CheckoutForm(request.POST)
    if not form.is_valid():
        return render(request, "mockpay/checkout.html", {"intent": intent, "form": form}, status=400)

    pan = form.cleaned_data["card_number"]
    chosen = form.cleaned_data["outcome"]
    outcome = chosen

    if chosen == "auto":
        if pan == "4242424242424242":
            outcome = "success"
        elif pan == "4000000000000002":
            outcome = "fail"
        elif pan == "4000000000009995":
            outcome = "challenge"
        else:
            outcome = "success"

    if outcome == "challenge":
        intent.status = PaymentIntentStatus.PROCESSING
        intent.save(update_fields=["status"])
        return redirect("mockpay:challenge", client_secret=client_secret)

    with transaction.atomic():
        intent.refresh_from_db()
        if outcome == "success":
            intent.status = PaymentIntentStatus.SUCCEEDED
            intent.save(update_fields=["status"])
            intent.reservation_group.status = ReservationStatus.RESERVED
            intent.reservation_group.save(update_fields=["status"])
            messages.success(request, "Payment successful.")
        elif outcome == "fail":
            intent.status = PaymentIntentStatus.FAILED
            intent.save(update_fields=["status"])
            messages.error(request, "Payment failed.")
        else:  # cancel
            intent.status = PaymentIntentStatus.CANCELED
            intent.save(update_fields=["status"])
            messages.info(request, "Payment canceled.")

    return redirect("mockpay:result", client_secret=client_secret)

@require_http_methods(["GET", "POST"])
def challenge(request, client_secret: str):
    """
    Mock 3-D Secure challenge.
    - GET: show a simple page asking the user to approve.
    - POST: approve = succeed payment and reserve group; cancel = cancel payment.
    We never store PAN/CVC; we may show last4/brand from session for UX only.
    """
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)

    if intent.is_expired():
        intent.status = PaymentIntentStatus.EXPIRED
        intent.save(update_fields=["status"])
        messages.error(request, "Payment session expired. Please try again.")
        return redirect("mockpay:result", client_secret=client_secret)

    if request.method == "GET":
        if intent.status != PaymentIntentStatus.PROCESSING:
            return redirect("mockpay:result", client_secret=client_secret)

        card_info = request.session.get("mockpay_tmp", {})
        context = {"intent": intent, "last4": card_info.get("last4"), "brand": card_info.get("brand", "card")}
        return render(request, "mockpay/challenge.html", context)

    decision = request.POST.get("decision")

    with transaction.atomic():
        intent.refresh_from_db()

        if intent.status != PaymentIntentStatus.PROCESSING:
            return redirect("mockpay:result", client_secret=client_secret)

        if decision == "approve":
            intent.status = PaymentIntentStatus.SUCCEEDED
            intent.save(update_fields=["status"])

            intent.reservation_group.status = ReservationStatus.RESERVED
            intent.reservation_group.save(update_fields=["status"])

            request.session.pop("mockpay_tmp", None)
            messages.success(request, "Payment approved.")
            return redirect("mockpay:result", client_secret=client_secret)

        intent.status = PaymentIntentStatus.CANCELED
        intent.save(update_fields=["status"])
        request.session.pop("mockpay_tmp", None)
        messages.info(request, "Payment canceled.")
        return redirect("mockpay:result", client_secret=client_secret)

@require_http_methods(["GET"])
def result(request, client_secret: str):
    intent = get_object_or_404(PaymentIntent, client_secret=client_secret)
    return render(request, "mockpay/result.html", {"intent": intent})
