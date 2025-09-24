from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction

from inventory.models.reservation import ReservationGroup, VehicleReservation, ReservationStatus

@login_required
@transaction.atomic
def cancel_reservation(request, group_id: int):
    group = get_object_or_404(ReservationGroup, pk=group_id, user=request.user)
    if request.method != "POST":
        return redirect("inventory:reservations")

    # Group → CANCELED, and all non-completed items → CANCELED
    group.status = ReservationStatus.CANCELED
    group.save(update_fields=["status"])
    VehicleReservation.objects.filter(group=group).exclude(
        status=ReservationStatus.COMPLETED
    ).update(status=ReservationStatus.CANCELED)

    messages.info(request, f"Reservation {group.reference} canceled.")
    return redirect("inventory:reservations")
