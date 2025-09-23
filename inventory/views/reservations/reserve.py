from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.redirect_back_to_search import redirect_back_to_search
from inventory.models.reservation import (
    Location,
    VehicleReservation,
    ReservationStatus,
)
from inventory.models.vehicle import Vehicle

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

    reservation = VehicleReservation(
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