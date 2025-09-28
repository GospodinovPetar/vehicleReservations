from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    ReservationGroup,
)


@login_required
def my_reservations(request: HttpRequest) -> HttpResponse:
    archived_statuses = [ReservationStatus.REJECTED, ReservationStatus.CANCELED]

    items_queryset = VehicleReservation.objects.select_related(
        "vehicle", "pickup_location", "return_location"
    ).order_by("-start_date")
    items_prefetch = Prefetch("reservations", queryset=items_queryset)

    base_groups = ReservationGroup.objects.filter(user=request.user)

    groups = (
        base_groups.exclude(status__in=archived_statuses)
        .prefetch_related(items_prefetch)
        .order_by("-created_at")
    )

    archived = (
        base_groups.filter(status__in=archived_statuses)
        .prefetch_related(items_prefetch)
        .order_by("-created_at")
    )

    context = {"groups": groups, "archived": archived}
    return render(request, "inventory/reservations.html", context)
