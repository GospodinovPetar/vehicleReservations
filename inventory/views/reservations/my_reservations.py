from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import render

from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    ReservationGroup
)


@login_required
def my_reservations(request):
    archived_statuses = [ReservationStatus.REJECTED, ReservationStatus.CANCELED]

    active_res_qs = (
        VehicleReservation.objects.exclude(status__in=archived_statuses)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("-start_date")
    )

    groups = (
        ReservationGroup.objects
        .filter(user=request.user)
        .exclude(status__in=archived_statuses)
        .prefetch_related(Prefetch("reservations", queryset=active_res_qs))
        .order_by("-created_at")
    )

    archived = (
        ReservationGroup.objects
        .filter(user=request.user, status__in=archived_statuses)
        .prefetch_related(
            "reservations__vehicle",
            "reservations__pickup_location",
            "reservations__return_location",
        )
        .order_by("-created_at")
    )

    ungroupped = (
        VehicleReservation.objects
        .filter(user=request.user, group__isnull=True)
        .exclude(status__in=archived_statuses)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("-start_date")
    )

    return render(
        request,
        "inventory/reservations.html",
        {
            "groups": groups,
            "archived": archived,
        },
    )