from django.contrib import messages
from django.shortcuts import render

from inventory.models.reservation import Location, Reservation
from inventory.models.vehicle import Vehicle
from inventory.views.helpers import parse_iso_date, compute_total


def home(request):
    locations = Location.objects.all()
    context = {"locations": locations}
    return render(request, "home.html", context)


def search(request):
    start_param = request.GET.get("start")
    end_param = request.GET.get("end")
    pickup_location_id = request.GET.get("pickup_location")
    return_location_id = request.GET.get("return_location")

    locations = Location.objects.all()
    context = {
        "locations": locations,
        "start": start_param,
        "end": end_param,
        "pickup_location": pickup_location_id,
        "return_location": return_location_id,
    }

    # both dates required
    if not start_param or not end_param:
        messages.error(request, "Please select both start and end dates.")
        return render(request, "home.html", context)

    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return render(request, "home.html", context)

    pickup_location = None
    if pickup_location_id:
        pickup_location = Location.objects.filter(id=pickup_location_id).first()

    return_location = None
    if return_location_id:
        return_location = Location.objects.filter(id=return_location_id).first()

    available_ids = Reservation.available_vehicles(
        start_date, end_date, pickup_location, return_location
    )
    vehicles = Vehicle.objects.filter(id__in=available_ids)

    results = []
    days_count = (end_date - start_date).days
    for v in vehicles:
        total_cost = compute_total(days_count, v.price_per_day)
        row = {
            "vehicle": v,
            "quote": {
                "days": int(days_count),
                "total": float(total_cost),
                "currency": "EUR",
            },
        }
        results.append(row)

    context["results"] = results
    return render(request, "home.html", context)
