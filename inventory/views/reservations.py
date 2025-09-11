from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from inventory.models.reservation import Location, Reservation, ReservationStatus
from inventory.models.vehicle import Vehicle
from inventory.views.helpers import parse_iso_date


@login_required
@require_http_methods(["POST"])
def reserve(request):
    data = request.POST

    vehicle = get_object_or_404(Vehicle, pk=data.get("vehicle"))
    start_date = parse_iso_date(data.get("start"))
    end_date = parse_iso_date(data.get("end"))

    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    pickup_location = None
    if data.get("pickup_location"):
        pickup_location = get_object_or_404(Location, pk=data.get("pickup_location"))
    else:
        pickup_location = vehicle.available_pickup_locations.first()

    return_location = None
    if data.get("return_location"):
        return_location = get_object_or_404(Location, pk=data.get("return_location"))
    else:
        # fall back to first allowed return location
        return_location = vehicle.available_return_locations.first()

    if pickup_location is None or return_location is None:
        messages.error(
            request, "This vehicle has no configured pickup/return locations."
        )
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    # Enforce allow-lists
    if not vehicle.available_pickup_locations.filter(pk=pickup_location.pk).exists():
        messages.error(
            request, "Selected pickup location is not available for this vehicle."
        )
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    if not vehicle.available_return_locations.filter(pk=return_location.pk).exists():
        messages.error(
            request, "Selected return location is not available for this vehicle."
        )
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    reservation = Reservation(
        user=request.user,
        vehicle=vehicle,
        pickup_location=pickup_location,
        return_location=return_location,
        start_date=start_date,
        end_date=end_date,
        status=ReservationStatus.RESERVED,
    )

    try:
        reservation.full_clean()
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    reservation.save()
    messages.success(request, "Reservation created.")
    return redirect("/reservations/")


@login_required
def reservations(request):
    user_reservations = (
        Reservation.objects.filter(user=request.user)
        .select_related("vehicle", "pickup_location", "return_location")
        .all()
    )
    context = {"reservations": user_reservations}
    return render(request, "reservations.html", context)


@login_required
@require_http_methods(["POST"])
def reject_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, user=request.user)
    if reservation.status not in (
        ReservationStatus.RESERVED,
        ReservationStatus.AWAITING_PICKUP,
    ):
        messages.error(
            request, "Only new or awaiting-pickup reservations can be rejected."
        )
        return redirect("/reservations/")
    reservation.status = ReservationStatus.REJECTED
    reservation.save(update_fields=["status"])
    messages.success(request, "Reservation rejected.")
    return redirect("/reservations/")
