from django.contrib import messages
from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import (
    login_required,
    user_passes_test,
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
    Managers/admins see groups split into:
    - ongoing: PENDING, AWAITING_PAYMENT, RESERVED
    - archived: COMPLETED, REJECTED, CANCELED
    """
    ongoing = (
        ReservationGroup.objects.filter(
            status__in=[
                ReservationStatus.PENDING,
                ReservationStatus.AWAITING_PAYMENT,
                ReservationStatus.RESERVED,
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
    """Update a group’s status instead of individual reservations."""
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
def reservation_group_complete(request, pk):
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.RESERVED:
        return HttpResponseForbidden("Only reserved groups can be marked as completed.")

    group.status = ReservationStatus.COMPLETED
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} marked as Completed.")
    return redirect("accounts:reservation-list")


# --- User reservation view (normal users only) ---
@login_required
def user_reservations(request):
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
