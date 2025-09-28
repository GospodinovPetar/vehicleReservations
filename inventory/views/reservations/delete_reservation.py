from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    ReservationGroup,
)
from mockpay.models import PaymentIntent, PaymentIntentStatus


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_reservation(request: HttpRequest, pk: int) -> HttpResponse:
    reservation_obj = get_object_or_404(
        VehicleReservation.objects.select_related("group"),
        pk=pk,
        user=request.user,
    )

    group_obj = reservation_obj.group
    if group_obj is None:
        messages.error(
            request, "You cannot remove the only vehicle in this reservation."
        )
        return redirect("inventory:reservations")

    group_obj = ReservationGroup.objects.select_for_update().get(pk=group_obj.pk)

    canceled_value = getattr(ReservationStatus, "CANCELED", "CANCELED")
    non_editable_statuses = [
        ReservationStatus.REJECTED,
        canceled_value,
        ReservationStatus.RESERVED,
    ]
    if group_obj.status in non_editable_statuses:
        messages.error(request, "This reservation cannot be modified.")
        return redirect("inventory:reservations")

    total_in_group = VehicleReservation.objects.filter(group=group_obj).count()
    if total_in_group <= 1:
        messages.error(
            request, "You cannot remove the only vehicle in this reservation."
        )
        return redirect("inventory:reservations")

    reservation_obj.delete()

    intents_qs = PaymentIntent.objects.select_for_update().filter(
        reservation_group=group_obj,
        status__in=[
            PaymentIntentStatus.REQUIRES_CONFIRMATION,
            PaymentIntentStatus.PROCESSING,
        ],
    )
    for intent in intents_qs:
        intent.status = PaymentIntentStatus.CANCELED
        intent.save(update_fields=["status"])

    messages.success(request, "Vehicle removed from reservation.")
    return redirect("inventory:reservations")
