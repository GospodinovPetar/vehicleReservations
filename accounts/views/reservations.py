from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Prefetch, Q
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import ReservationStatusForm
from accounts.views.admins_managers import manager_required
from inventory.models.reservation import (
    ReservationGroup,
    ReservationStatus,
    VehicleReservation, Location,
)


from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Prefetch
from django.shortcuts import render

from inventory.models.vehicle import Vehicle


def reservation_list(request):
    user_q = request.GET.get("user", "").strip()
    pickup_q = request.GET.get("pickup", "").strip()
    dropoff_q = request.GET.get("dropoff", "").strip()
    status_q = request.GET.get("status", "").strip()

    reservations_qs = (
        VehicleReservation.objects
        .select_related("user", "pickup_location", "return_location", "vehicle")
    )
    if user_q:
        reservations_qs = reservations_qs.filter(
            Q(user__first_name__icontains=user_q) | Q(user__last_name__icontains=user_q)
        )
    if pickup_q:
        reservations_qs = reservations_qs.filter(
            Q(pickup_location__name__iexact=pickup_q) |
            Q(pickup_location_snapshot__iexact=pickup_q)
        )
    if dropoff_q:
        reservations_qs = reservations_qs.filter(
            Q(return_location__name__iexact=dropoff_q) |
            Q(return_location_snapshot__iexact=dropoff_q)
        )

    prefetch_filtered = Prefetch("reservations", queryset=reservations_qs, to_attr="filtered_reservations")

    ongoing_statuses  = ["PENDING", "AWAITING_PAYMENT", "RESERVED", "ONGOING"]
    archived_statuses = ["COMPLETED", "REJECTED", "CANCELED"]

    ongoing_qs  = ReservationGroup.objects.filter(status__in=ongoing_statuses)
    archived_qs = ReservationGroup.objects.filter(status__in=archived_statuses)

    if status_q:
        ongoing_qs  = ongoing_qs.filter(status=status_q)
        archived_qs = archived_qs.filter(status=status_q)

    ongoing_qs = (
        ongoing_qs.filter(reservations__in=reservations_qs)
        .prefetch_related(prefetch_filtered)
        .distinct()
        .order_by("-created_at")
    )
    archived_qs = (
        archived_qs.filter(reservations__in=reservations_qs)
        .prefetch_related(prefetch_filtered)
        .distinct()
        .order_by("-created_at")
    )

    ongoing_page_num  = request.GET.get("ongoing_page", 1)
    archived_page_num = request.GET.get("archived_page", 1)

    ongoing_paginator  = Paginator(ongoing_qs, 3)
    archived_paginator = Paginator(archived_qs, 4)

    try:
        ongoing_page_obj = ongoing_paginator.page(ongoing_page_num)
    except (PageNotAnInteger, EmptyPage):
        ongoing_page_obj = ongoing_paginator.page(1)

    try:
        archived_page_obj = archived_paginator.page(archived_page_num)
    except (PageNotAnInteger, EmptyPage):
        archived_page_obj = archived_paginator.page(1)

    qs = request.GET.copy()

    ongoing_params = qs.copy()
    ongoing_params.pop("ongoing_page", None)
    ongoing_params = ongoing_params.urlencode()

    archived_params = qs.copy()
    archived_params.pop("archived_page", None)
    archived_params = archived_params.urlencode()

    locations = list(
        Location.objects.order_by("name").values_list("name", flat=True).distinct()
    )

    vehicles = Vehicle.objects.order_by("name").all()

    return render(request, "accounts/reservations/reservation_list.html", {
        "ongoing_page_obj": ongoing_page_obj,
        "archived_page_obj": archived_page_obj,
        "ongoing_total": ongoing_paginator.count,
        "archived_total": archived_paginator.count,
        "locations": locations,
        "ongoing_params": ongoing_params,
        "archived_params": archived_params,
        "vehicles": vehicles,
    })


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_group_approve(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Move a pending reservation group to AWAITING_PAYMENT.

    Args:
        pk (int): ReservationGroup primary key.

    Returns:
        403 if the group is not in PENDING.
    """
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.PENDING:
        return HttpResponseForbidden("Only pending groups can be approved.")

    group.status = ReservationStatus.AWAITING_PAYMENT
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} is now awaiting payment.")
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_group_reject(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Reject a reservation group.

    Allowed from statuses: PENDING, AWAITING_PAYMENT.

    Args:
        pk (int): ReservationGroup primary key.

    Returns:
        403 if the group is not in an allowed status.
    """
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status not in (
        ReservationStatus.PENDING,
        ReservationStatus.AWAITING_PAYMENT,
    ):
        return HttpResponseForbidden(
            "Only pending/awaiting-payment groups can be rejected."
        )

    group.status = ReservationStatus.REJECTED
    group.save(update_fields=["status"])

    messages.warning(request, f"Reservation group {group.id} has been rejected.")
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_update(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Update a group’s status via form (only for PENDING groups).

    - GET: render form with current status.
    - POST: validate and save the group status.

    Args:
        pk (int): ReservationGroup primary key.

    Returns:
        403 if the group is not PENDING.
    """
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.PENDING:
        return HttpResponseForbidden("Only pending groups can be updated.")

    if request.method == "POST":
        form = ReservationStatusForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, f"Reservation group {group.id} updated.")
            return redirect("accounts:reservation-list")
    else:
        form = ReservationStatusForm(instance=group)

    return render(
        request,
        "accounts/reservations/reservation_update.html",
        {"form": form, "group": group},
    )


# @login_required
# @manager_required
# @permission_required("inventory.change_reservationgroup", raise_exception=True)
# def reservation_approve(request: HttpRequest, pk: int) -> HttpResponse:
#     """
#     Approve a reservation by moving its group to AWAITING_PAYMENT.
#
#     Args:
#         pk (int): VehicleReservation primary key.
#
#     Returns:
#         403 if the group is missing or not PENDING.
#     """
#     reservation = get_object_or_404(VehicleReservation, pk=pk)
#     group = reservation.group
#     if not group or group.status != ReservationStatus.PENDING:
#         return HttpResponseForbidden("Only pending reservation groups can be approved.")
#
#     group.status = ReservationStatus.AWAITING_PAYMENT
#     group.save(update_fields=["status"])
#
#     messages.success(request, f"Reservation #{reservation.id} is now awaiting payment.")
#     return redirect("accounts:reservation-list")


# @login_required
# @manager_required
# @permission_required("inventory.change_reservationgroup", raise_exception=True)
# def reservation_reject(request: HttpRequest, pk: int) -> HttpResponse:
#     """
#     Reject a reservation by moving its group to REJECTED.
#
#     Allowed from statuses: PENDING, AWAITING_PAYMENT.
#
#     Args:
#         pk (int): VehicleReservation primary key.
#
#     Returns:
#         403 if the group is missing or not in an allowed status.
#     """
#     reservation = get_object_or_404(VehicleReservation, pk=pk)
#     group = reservation.group
#     if not group or group.status not in (
#         ReservationStatus.PENDING,
#         ReservationStatus.AWAITING_PAYMENT,
#     ):
#         return HttpResponseForbidden(
#             "Only pending/awaiting-payment reservation groups can be rejected."
#         )
#
#     group.status = ReservationStatus.REJECTED
#     group.save(update_fields=["status"])
#
#     messages.warning(
#         request, f"Reservation #{reservation.id} rejected; group moved to Rejected."
#     )
#     return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Cancel a reservation by moving its group to CANCELED.

    Allowed from status: RESERVED.

    Args:
        pk (int): VehicleReservation primary key.

    Returns:
        403 if the group is missing or not RESERVED.
    """
    reservation = get_object_or_404(VehicleReservation, pk=pk)
    group = reservation.group
    if not group or group.status == ReservationStatus.COMPLETED or group.status == ReservationStatus.ONGOING:
        return HttpResponseForbidden(
            "Only future reservations can be canceled."
        )

    group.status = ReservationStatus.CANCELED
    group.save(update_fields=["status"])

    messages.warning(
        request, f"Reservation #{reservation.id} canceled; group moved to Archived."
    )
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_complete(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Mark a reservation group as COMPLETED (group provided by pk).

    Args:
        pk (int): ReservationGroup primary key (despite the name).

    Returns:
        403 if the group is not RESERVED.
    """
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.RESERVED:
        return HttpResponseForbidden("Only reserved groups can be marked as completed.")

    group.status = ReservationStatus.COMPLETED
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} marked as Completed.")
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_group_ongoing(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Mark a reservation group as COMPLETED (explicit group endpoint).

    Args:
        pk (int): ReservationGroup primary key.

    Returns:
        403 if the group is not RESERVED.
    """
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.RESERVED:
        return HttpResponseForbidden("Only reserved groups can be marked as ongoing.")

    group.status = ReservationStatus.ONGOING
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} marked as Ongoing.")
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_group_complete(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Mark a reservation group as COMPLETED (explicit group endpoint).

    Args:
        pk (int): ReservationGroup primary key.

    Returns:
        403 if the group is not RESERVED.
    """
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.ONGOING:
        return HttpResponseForbidden("Only ongoing groups can be marked as completed.")

    group.status = ReservationStatus.COMPLETED
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} marked as Completed.")
    return redirect("accounts:reservation-list")



