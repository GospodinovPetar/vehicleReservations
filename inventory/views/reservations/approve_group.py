from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect

from inventory.models.reservation import ReservationGroup, VehicleReservation, ReservationStatus

@user_passes_test(lambda u: u.is_staff)
@transaction.atomic
def approve_group(request, group_id: int):
    group = get_object_or_404(ReservationGroup.objects.select_for_update(), pk=group_id)

    if group.status != ReservationStatus.PENDING:
        messages.info(request, "Group is not pending.")
        return redirect("inventory:reservations")

    group.status = ReservationStatus.AWAITING_PAYMENT
    group.save(update_fields=["status"])
    VehicleReservation.objects.filter(group=group, status=ReservationStatus.PENDING)\
                              .update(status=ReservationStatus.AWAITING_PAYMENT)

    messages.success(request, f"Reservation {group.reference} approved. Awaiting payment.")
    return redirect("inventory:reservations")
