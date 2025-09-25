from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from inventory.models.reservation import (
    Location,
    VehicleReservation,
    ReservationStatus,
    BLOCKING_STATUSES,
)
from inventory.models.vehicle import Vehicle
from django.utils import timezone

from inventory.views.reservations.reservation_edit_form import ReservationEditForm


@login_required
def edit_reservation(request, pk):
    """
    Allow a user to edit their reservation. If the user changes pickup/return dates,
    we check whether the selected vehicle is available for those dates (ignoring the
    current reservation itself). If available, we save the new dates and set the
    GROUP status back to PENDING for re-approval.
    """
    reservation = get_object_or_404(
        VehicleReservation.objects.select_related("vehicle", "group"),
        pk=pk,
        user=request.user,
    )

    if request.method == "POST":
        form = ReservationEditForm(request.POST, instance=reservation)

        if form.is_valid():
            selected_vehicle = form.cleaned_data.get("vehicle")
            selected_pickup = form.cleaned_data.get("pickup_location")
            selected_return = form.cleaned_data.get("return_location")
            new_start = form.cleaned_data.get("start_date")
            new_end = form.cleaned_data.get("end_date")

            original_start = reservation.start_date
            original_end = reservation.end_date

            if not new_start or not new_end:
                form.add_error(None, "Please provide both pickup and return dates.")
            else:
                if new_start >= new_end:
                    form.add_error("end_date", "End date must be after start date.")

                today = timezone.localdate()
                if new_start < today:
                    form.add_error("start_date", "Pickup date cannot be in the past.")
                if new_end < today:
                    form.add_error("end_date", "Return date cannot be in the past.")

            if (
                selected_vehicle
                and selected_pickup
                and selected_vehicle.available_pickup_locations.exists()
            ):
                if not selected_vehicle.available_pickup_locations.filter(
                    pk=selected_pickup.pk
                ).exists():
                    form.add_error(
                        "pickup_location",
                        "Pickup location not allowed for this vehicle.",
                    )

            if (
                selected_vehicle
                and selected_return
                and selected_vehicle.available_return_locations.exists()
            ):
                if not selected_vehicle.available_return_locations.filter(
                    pk=selected_return.pk
                ).exists():
                    form.add_error(
                        "return_location",
                        "Return location not allowed for this vehicle.",
                    )

            if form.errors:
                return render(
                    request,
                    "inventory/edit_reservation.html",
                    {
                        "form": form,
                        "reservation": reservation,
                        "vehicles": Vehicle.objects.all().order_by("name"),
                        "locations": Location.objects.all().order_by("name"),
                    },
                )

            overlaps = VehicleReservation.objects.filter(
                vehicle_id=selected_vehicle.pk,
                group__status__in=BLOCKING_STATUSES,
                start_date__lt=new_end,
                end_date__gt=new_start,
            ).exclude(pk=reservation.pk)

            if overlaps.exists():
                form.add_error(
                    "start_date",
                    "This vehicle is not available in the selected period.",
                )
                return render(
                    request,
                    "inventory/edit_reservation.html",
                    {
                        "form": form,
                        "reservation": reservation,
                        "vehicles": Vehicle.objects.all().order_by("name"),
                        "locations": Location.objects.all().order_by("name"),
                    },
                )

            try:
                with transaction.atomic():
                    instance = form.save(commit=False)
                    instance.full_clean()
                    instance.save()

                    dates_changed = (
                        ("start_date" in form.changed_data)
                        or ("end_date" in form.changed_data)
                        or original_start != new_start
                        or original_end != new_end
                    )

                    if dates_changed and instance.group_id:
                        instance.group.status = ReservationStatus.PENDING
                        instance.group.save(update_fields=["status"])

                messages.success(
                    request,
                    "Reservation updated."
                    + (
                        " Status set to PENDING for re-approval."
                        if dates_changed
                        else ""
                    ),
                )
                return redirect("inventory:reservations")

            except Exception as exc:
                form.add_error(None, str(exc))

    else:
        form = ReservationEditForm(instance=reservation)

    vehicles = Vehicle.objects.all().order_by("name")
    locations = Location.objects.all().order_by("name")
    return render(
        request,
        "inventory/edit_reservation.html",
        {
            "form": form,
            "reservation": reservation,
            "vehicles": vehicles,
            "locations": locations,
        },
    )
