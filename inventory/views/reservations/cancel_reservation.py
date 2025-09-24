from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from inventory.models.reservation import ReservationGroup, ReservationStatus
from mockpay.models import PaymentIntent, PaymentIntentStatus

@login_required
@require_http_methods(["POST"])
def cancel_reservation(request, group_id: int):
    group = get_object_or_404(ReservationGroup, id=group_id, user=request.user)

    with transaction.atomic():
        group.reservations.update(status=ReservationStatus.CANCELED)
        group.status = ReservationStatus.CANCELED
        group.save(update_fields=["status"])

        intents = PaymentIntent.objects.filter(reservation_group=group)
        for intent in intents.select_for_update():
            if intent.status in (
                PaymentIntentStatus.REQUIRES_CONFIRMATION,
                PaymentIntentStatus.PROCESSING,
            ):
                intent.status = PaymentIntentStatus.CANCELED
                intent.save(update_fields=["status"])

    messages.info(request, f"Reservation {group.reference} canceled.")
    return redirect("inventory:reservations")
