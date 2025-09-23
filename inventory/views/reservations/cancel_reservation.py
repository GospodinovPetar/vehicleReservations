from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect

from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    ReservationGroup
)

@login_required
def cancel_reservation(request, group_id):
    group = get_object_or_404(ReservationGroup, pk=group_id, user=request.user)
    reference = group.reference or f"#{group.pk}"

    with transaction.atomic():
        cancelable = ~Q(status=ReservationStatus.REJECTED)
        if hasattr(ReservationStatus, "COMPLETED"):
            cancelable &= ~Q(status=ReservationStatus.COMPLETED)

        updated = VehicleReservation.objects.filter(group=group).filter(cancelable)
        for r in updated.only("id", "status"):
            r.status = getattr(ReservationStatus, "CANCELED", "CANCELED")
            r.save(update_fields=["status"])

        group.delete()

    messages.success(request, f"Canceled {updated} reservation(s)")
    return redirect("inventory:reservations")