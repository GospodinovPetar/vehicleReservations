from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
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
def delete_reservation(request, pk):
    reservation = get_object_or_404(
        VehicleReservation.objects.select_related("group"),
        pk=pk,
        user=request.user,
    )

    canceled_value = getattr(ReservationStatus, "CANCELED", "CANCELED")
    non_active_statuses = [ReservationStatus.REJECTED, canceled_value]

    group = reservation.group
    if group is None:
        messages.error(request, "You cannot remove the only vehicle in this reservation.")
        return redirect("inventory:reservations")

    ReservationGroup.objects.select_for_update().filter(pk=group.pk).exists()

    active_in_group = (
        VehicleReservation.objects.filter(group=group)
        .exclude(status__in=non_active_statuses)
        .count()
    )
    if active_in_group <= 1:
        messages.error(request, "You cannot remove the only vehicle in this reservation.")
        return redirect("inventory:reservations")

    reservation.delete()

    for intent in (
        PaymentIntent.objects.select_for_update()
        .filter(reservation_group=group,
                status__in=[PaymentIntentStatus.REQUIRES_CONFIRMATION,
                            PaymentIntentStatus.PROCESSING])
    ):
        intent.status = PaymentIntentStatus.CANCELED
        intent.save(update_fields=["status"])

    messages.success(request, "Vehicle removed from reservation.")
    return redirect("inventory:reservations")
