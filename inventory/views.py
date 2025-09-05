from datetime import date
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Vehicle, Location, Reservation
from .pricing import RateTable, quote_total


def home(request):
    """
    Render the home page with the list of locations.
    """
    all_locations = Location.objects.all()
    context = {"locations": all_locations}
    return render(request, "home.html", context)


def search(request):
    """
    Show available vehicles and quotes for the selected date range and locations.
    """
    start_date_param = request.GET.get("start")
    end_date_param = request.GET.get("end")
    pickup_location_id = request.GET.get("pickup_location")
    return_location_id = request.GET.get("return_location")

    all_locations = Location.objects.all()
    context = {
        "locations": all_locations,
        "start": start_date_param,
        "end": end_date_param,
        "pickup_location": pickup_location_id,
        "return_location": return_location_id,
    }

    if not start_date_param or not end_date_param:
        return render(request, "home.html", context)

    start_date = date.fromisoformat(start_date_param)
    end_date = date.fromisoformat(end_date_param)

    if pickup_location_id:
        pickup_location = Location.objects.filter(id=pickup_location_id).first()
    else:
        pickup_location = None

    if return_location_id:
        return_location = Location.objects.filter(id=return_location_id).first()
    else:
        return_location = None

    # Determine available vehicles for the request
    available_vehicle_ids = Reservation.available_vehicle_ids(
        start_date, end_date, pickup_location, return_location
    )

    vehicle_queryset = Vehicle.objects.filter(id__in=available_vehicle_ids).prefetch_related(
        "prices", "vehicle_locations__location"
    )

    results = []
    for vehicle in vehicle_queryset:
        period_prices = {}
        for price in vehicle.prices.all():
            period_type = price.period_type
            amount_value = float(price.amount)
            period_prices[period_type] = amount_value

        rate_table = RateTable(
            day=period_prices.get("day"),
            week=period_prices.get("week"),
            month=period_prices.get("month"),
            currency=vehicle.currency,
        )
        quote_info = quote_total(start_date, end_date, rate_table)

        result_item = {"vehicle": vehicle, "quote": quote_info}
        results.append(result_item)

    context["results"] = results
    return render(request, "home.html", context)


@require_http_methods(["POST"])
def reserve(request):
    """
    Create a reservation for the selected vehicle and dates.
    """
    form_data = request.POST
    vehicle_id = form_data.get("vehicle")
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    # Choose provided locations or sensible defaults from the vehicle availability
    pickup_location_id = form_data.get("pickup_location")
    return_location_id = form_data.get("return_location")

    if pickup_location_id:
        pickup_location = get_object_or_404(Location, id=pickup_location_id)
    else:
        vehicle_location_pickup = (
            vehicle.vehicle_locations.filter(can_pickup=True)
            .select_related("location")
            .first()
        )
        pickup_location = vehicle_location_pickup.location

    if return_location_id:
        return_location = get_object_or_404(Location, id=return_location_id)
    else:
        # Default to a 'can_return' spot; prefer default_return locations when available
        vehicle_location_queryset = (
            vehicle.vehicle_locations.filter(can_return=True)
            .select_related("location")
        )
        preferred_return = vehicle_location_queryset.filter(
            location__is_default_return=True
        ).first()
        if preferred_return:
            return_location = preferred_return.location
        else:
            any_return = vehicle_location_queryset.first()
            return_location = any_return.location

    start_date = date.fromisoformat(form_data.get("start"))
    end_date = date.fromisoformat(form_data.get("end"))

    reservation = Reservation(
        user=request.user,
        vehicle=vehicle,
        pickup_location=pickup_location,
        return_location=return_location,
        start_date=start_date,
        end_date=end_date,
        currency=vehicle.currency,
    )

    try:
        reservation.clean()
    except Exception as error:
        messages.error(request, str(error))
        return redirect(f"/search/?start={start_date.isoformat()}&end={end_date.isoformat()}")

    # Compute price
    period_prices = {}
    for price in vehicle.prices.all():
        period_type = price.period_type
        amount_value = float(price.amount)
        period_prices[period_type] = amount_value

    rate_table = RateTable(
        day=period_prices.get("day"),
        week=period_prices.get("week"),
        month=period_prices.get("month"),
        currency=vehicle.currency,
    )
    quote_info = quote_total(start_date, end_date, rate_table)

    reservation.total_price = quote_info["total"]
    reservation.save()

    messages.success(request, "Reservation created!")
    return redirect("/reservations/")


def reservations(request):
    """
    List the user's reservations.
    """
    reservation_queryset = (
        Reservation.objects.filter(user=request.user)
        .select_related("vehicle", "pickup_location", "return_location")
        .all()
    )
    context = {"reservations": reservation_queryset}
    return render(request, "reservations.html", context)


@require_http_methods(["POST"])
def cancel_reservation(request, pk):
    """
    Cancel a reservation if it is pending or confirmed.
    """
    from django.http import Http404

    try:
        reservation = Reservation.objects.get(pk=pk, user=request.user)
    except Reservation.DoesNotExist:
        raise Http404

    if reservation.status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "Cannot cancel this reservation.")
    else:
        reservation.status = "CANCELLED"
        reservation.save(update_fields=["status"])
        messages.success(request, "Reservation cancelled.")

    return redirect("/reservations/")


@require_http_methods(["POST"])
def reject_reservation(request, pk):
    """
    Reject a reservation if it is pending.
    """
    from django.http import Http404

    try:
        reservation = Reservation.objects.get(pk=pk, user=request.user)
    except Reservation.DoesNotExist:
        raise Http404

    if reservation.status != "PENDING":
        messages.error(request, "Only pending reservations can be rejected.")
    else:
        reservation.status = "REJECTED"
        reservation.save(update_fields=["status"])
        messages.success(request, "Reservation rejected.")

    return redirect("/reservations/")
