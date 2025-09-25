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

    items_prefetch = Prefetch(
        "reservations",
        queryset=VehicleReservation.objects.select_related(
            "vehicle", "pickup_location", "return_location"
        ).order_by("-start_date"),
    )

    groups = (
        ReservationGroup.objects
        .filter(user=request.user)
        .exclude(status__in=archived_statuses)
        .prefetch_related(items_prefetch)
        .order_by("-created_at")
    )

    archived = (
        ReservationGroup.objects
        .filter(user=request.user, status__in=archived_statuses)
        .prefetch_related(items_prefetch)
        .order_by("-created_at")
    )

    return render(
        request,
        "inventory/reservations.html",
        {"groups": groups, "archived": archived},
    )