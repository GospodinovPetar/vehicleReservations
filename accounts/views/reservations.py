from django.contrib import messages
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import redirect, render, get_object_or_404

from accounts.forms import ReservationStatusForm
from accounts.views.admins_managers import manager_required
from inventory.models.reservation import (
    ReservationGroup,
    ReservationStatus,
    VehicleReservation,
)


@login_required
@manager_required
@permission_required("inventory.view_reservationgroup", raise_exception=True)
def reservation_list(request):
    """
    List reservation groups for managers/admins, split by status.

    Ongoing statuses: PENDING, AWAITING_PAYMENT, RESERVED.
    Archived statuses: COMPLETED, REJECTED, CANCELED.

    Renders:
        accounts/reservations/reservation_list.html

    Context:
        ongoing (QuerySet[ReservationGroup])
        archived (QuerySet[ReservationGroup])
    """
    ongoing = (
        ReservationGroup.objects.filter(
            status__in=[
                ReservationStatus.PENDING,
                ReservationStatus.AWAITING_PAYMENT,
                ReservationStatus.RESERVED,
                ReservationStatus.ONGOING
            ]
        )
        .prefetch_related("reservations__vehicle", "reservations__user")
        .order_by("-created_at")
    )

    archived = (
        ReservationGroup.objects.filter(
            status__in=[
                ReservationStatus.COMPLETED,
                ReservationStatus.REJECTED,
                ReservationStatus.CANCELED,
            ]
        )
        .prefetch_related("reservations__vehicle", "reservations__user")
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/reservations/reservation_list.html",
        {"ongoing": ongoing, "archived": archived},
    )


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_group_approve(request, pk):
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
def reservation_group_reject(request, pk):
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
def reservation_update(request, pk):
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


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_approve(request, pk):
    """
    Approve a reservation by moving its group to AWAITING_PAYMENT.

    Args:
        pk (int): VehicleReservation primary key.

    Returns:
        403 if the group is missing or not PENDING.
    """
    reservation = get_object_or_404(VehicleReservation, pk=pk)
    grp = reservation.group
    if not grp or grp.status != ReservationStatus.PENDING:
        return HttpResponseForbidden("Only pending reservation groups can be approved.")

    grp.status = ReservationStatus.AWAITING_PAYMENT
    grp.save(update_fields=["status"])

    messages.success(request, f"Reservation #{reservation.id} is now awaiting payment.")
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_reject(request, pk):
    """
    Reject a reservation by moving its group to REJECTED.

    Allowed from statuses: PENDING, AWAITING_PAYMENT.

    Args:
        pk (int): VehicleReservation primary key.

    Returns:
        403 if the group is missing or not in an allowed status.
    """
    r = get_object_or_404(VehicleReservation, pk=pk)
    grp = r.group
    if not grp or grp.status not in (
        ReservationStatus.PENDING,
        ReservationStatus.AWAITING_PAYMENT,
    ):
        return HttpResponseForbidden(
            "Only pending/awaiting-payment reservation groups can be rejected."
        )

    grp.status = ReservationStatus.REJECTED
    grp.save(update_fields=["status"])

    messages.warning(request, f"Reservation #{r.id} rejected; group moved to Rejected.")
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_cancel(request, pk):
    """
    Cancel a reservation by moving its group to CANCELED.

    Allowed from status: RESERVED.

    Args:
        pk (int): VehicleReservation primary key.

    Returns:
        403 if the group is missing or not RESERVED.
    """
    r = get_object_or_404(VehicleReservation, pk=pk)
    grp = r.group
    if not grp or grp.status != ReservationStatus.RESERVED:
        return HttpResponseForbidden(
            "Only reserved reservation groups can be canceled."
        )

    grp.status = ReservationStatus.CANCELED
    grp.save(update_fields=["status"])

    messages.warning(request, f"Reservation #{r.id} canceled; group moved to Canceled.")
    return redirect("accounts:reservation-list")


@login_required
@manager_required
@permission_required("inventory.change_reservationgroup", raise_exception=True)
def reservation_complete(request, pk):
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
def reservation_group_ongoing(request, pk):
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
def reservation_group_complete(request, pk):
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


@login_required
def user_reservations(request):
    """
    List the logged-in user's individual vehicle reservations.

    Renders:
        accounts/reservations/reservation_list_user.html

    Context:
        reservations (QuerySet[VehicleReservation]): Reservations for request.user.
    """
    reservations = (
        VehicleReservation.objects.filter(user=request.user)
        .select_related("vehicle", "pickup_location", "return_location")
        .all()
    )
    return render(
        request,
        "accounts/reservations/reservation_list_user.html",
        {"reservations": reservations},
    )
