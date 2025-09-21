from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.redirect_back_to_search import redirect_back_to_search
from inventory.models.cart import ReservationGroup
from inventory.models.reservation import Location, Reservation, ReservationStatus, BLOCKING_STATUSES
from inventory.models.vehicle import Vehicle
from django.utils import timezone


class ReservationEditForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = [
            "vehicle",
            "pickup_location",
            "return_location",
            "start_date",
            "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


@login_required
@require_http_methods(["POST"])
def reserve(request):
    form_data = request.POST

    vehicle = get_object_or_404(Vehicle, pk=form_data.get("vehicle"))
    start_date = parse_iso_date(form_data.get("start"))
    end_date = parse_iso_date(form_data.get("end"))

    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return redirect_back_to_search(form_data.get("start"), form_data.get("end"))

    if form_data.get("pickup_location"):
        pickup_location = get_object_or_404(
            Location, pk=form_data.get("pickup_location")
        )
    else:
        pickup_location = vehicle.available_pickup_locations.first()

    if form_data.get("return_location"):
        return_location = get_object_or_404(
            Location, pk=form_data.get("return_location")
        )
    else:
        return_location = vehicle.available_return_locations.first()

    if pickup_location is None or return_location is None:
        messages.error(
            request, "This vehicle has no configured pickup/return locations."
        )
        return redirect_back_to_search(form_data.get("start"), form_data.get("end"))

    if not vehicle.available_pickup_locations.filter(pk=pickup_location.pk).exists():
        messages.error(
            request, "Selected pickup location is not available for this vehicle."
        )
        return redirect_back_to_search(form_data.get("start"), form_data.get("end"))

    if not vehicle.available_return_locations.filter(pk=return_location.pk).exists():
        messages.error(
            request, "Selected return location is not available for this vehicle."
        )
        return redirect_back_to_search(form_data.get("start"), form_data.get("end"))

    reservation = Reservation(
        user=request.user,
        vehicle=vehicle,
        pickup_location=pickup_location,
        return_location=return_location,
        start_date=start_date,
        end_date=end_date,
        status=ReservationStatus.PENDING,
    )

    try:
        reservation.full_clean()
        reservation.save()
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect_back_to_search(form_data.get("start"), form_data.get("end"))

    messages.success(request, "Reservation created.")
    return redirect("inventory:reservations")


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
        "inventory/my_reservations.html",
        {"groups": groups, "ungroupped": ungroupped, "canceled": canceled},
    )


@login_required
def edit_reservation(request, pk):
    """
    Allow a user to edit their reservation. If the user changes pickup/return dates,
    we check whether the selected vehicle is available for those dates (ignoring the
    current reservation itself). If available, we save the new dates and set status
    back to PENDING for re-approval.
    """
    reservation = get_object_or_404(
        Reservation.objects.select_related("vehicle", "group"),
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

            if selected_vehicle and selected_pickup and selected_vehicle.available_pickup_locations.exists():
                if not selected_vehicle.available_pickup_locations.filter(pk=selected_pickup.pk).exists():
                    form.add_error("pickup_location", "Pickup location not allowed for this vehicle.")

            if selected_vehicle and selected_return and selected_vehicle.available_return_locations.exists():
                if not selected_vehicle.available_return_locations.filter(pk=selected_return.pk).exists():
                    form.add_error("return_location", "Return location not allowed for this vehicle.")

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

            overlaps = Reservation.objects.filter(
                vehicle_id=selected_vehicle.pk,
                status__in=BLOCKING_STATUSES,
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
                            ("start_date" in form.changed_data) or ("end_date" in form.changed_data)
                            or original_start != new_start
                            or original_end != new_end
                    )

                    if dates_changed:
                        instance.status = ReservationStatus.PENDING
                        instance.save(update_fields=["status"])  # triggers your status-change signal

                messages.success(
                    request,
                    "Reservation updated." + (" Status set to PENDING for re-approval." if dates_changed else "")
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



@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_reservation(request, pk):
    reservation = get_object_or_404(
        Reservation.objects.select_related("group"),
        pk=pk,
        user=request.user,
    )

    canceled_value = getattr(ReservationStatus, "CANCELED", "CANCELED")
    non_active_statuses = [ReservationStatus.REJECTED, canceled_value]

    group = reservation.group
    if group is None:
        messages.error(
            request, "You cannot remove the only vehicle in this reservation."
        )
        return redirect("inventory:reservations")

    ReservationGroup.objects.select_for_update().filter(pk=group.pk).exists()

    active_in_group = (
        Reservation.objects.filter(group=group)
        .exclude(status__in=non_active_statuses)
        .count()
    )
    if active_in_group <= 1:
        messages.error(
            request, "You cannot remove the only vehicle in this reservation."
        )
        return redirect("inventory:reservations")

    reservation.delete()
    messages.success(request, "Vehicle removed from reservation.")
    return redirect("inventory:reservations")


@login_required
def cancel_group(request, group_id):
    group = get_object_or_404(ReservationGroup, pk=group_id, user=request.user)
    reference = group.reference or f"#{group.pk}"

    with transaction.atomic():
        cancelable = ~Q(status=ReservationStatus.REJECTED)
        if hasattr(ReservationStatus, "COMPLETED"):
            cancelable &= ~Q(status=ReservationStatus.COMPLETED)

        updated = (
            Reservation.objects.filter(group=group)
            .filter(cancelable)
        )
        for r in updated.only("id", "status"):
            r.status = getattr(ReservationStatus, "CANCELED", "CANCELED")
            r.save(update_fields=["status"])

        group.delete()

    messages.success(request, f"Canceled {updated} reservation(s)")
    return redirect("inventory:reservations")


@login_required
@require_http_methods(["POST"])
def reject_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, user=request.user)

    if reservation.status in (
        ReservationStatus.CANCELED,
        ReservationStatus.COMPLETED,
        ReservationStatus.REJECTED,
    ):
        messages.error(request, "Only ongoing reservations can be rejected.")
        return redirect("inventory:reservations")

    reservation.status = ReservationStatus.REJECTED
    reservation.save(update_fields=["status"])

    messages.success(request, "Reservation rejected.")
    return redirect("inventory:reservations")
