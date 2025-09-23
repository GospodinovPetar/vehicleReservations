from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from inventory.models.reservation import (
    Reservation,
    ReservationStatus,
)

@login_required
@require_http_methods(["POST"])
def reject_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, user=request.user)

    if reservation.status in (
        ReservationStatus.CANCELED,
        ReservationStatus.COMPLETED,
        ReservationStatus.REJECTED,
    ):
        messages.error(request, "Only ongoing reservations can be rejected.")
        return redirect("inventory:reservations")

    reservation.status = ReservationStatus.REJECTED
    reservation.save(update_fields=["status"])

    messages.success(request, "Reservation rejected.")
    return redirect("inventory:reservations")