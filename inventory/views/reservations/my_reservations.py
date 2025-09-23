from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import render

from inventory.models.reservation import (
    Reservation,
    ReservationStatus,
    ReservationGroup
)


@login_required
def my_reservations(request):
    non_active_statuses = [
        ReservationStatus.REJECTED,
        getattr(ReservationStatus, "CANCELED", "CANCELED"),
    ]

    active_reservations_qs = (
        Reservation.objects.exclude(status__in=non_active_statuses)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("-start_date")
    )

    groups = (
        ReservationGroup.objects.filter(user=request.user)
        .prefetch_related(Prefetch("reservations", queryset=active_reservations_qs))
        .order_by("-created_at")
    )

    ungroupped = (
        Reservation.objects.filter(user=request.user, group__isnull=True)
        .exclude(status__in=non_active_statuses)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("-start_date")
    )

    canceled = (
        Reservation.objects.filter(
            user=request.user, status=getattr(ReservationStatus, "CANCELED", "CANCELED")
        )
        .select_related("vehicle", "pickup_location", "return_location", "group")
        .order_by("-start_date")
    )

    rejected = (
        Reservation.objects.filter(user=request.user, status=ReservationStatus.REJECTED)
        .select_related("vehicle", "pickup_location", "return_location", "group")
        .order_by("-start_date")
    )

    return render(
        request,
        "inventory/reservations.html",
        {"groups": groups, "ungroupped": ungroupped, "canceled": canceled},
    )