from django.contrib import messages
from django.shortcuts import render

from inventory.models.cart import CartItem
from inventory.models.reservation import Location, Reservation
from inventory.models.vehicle import Vehicle
from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.pricing import RateTable, quote_total


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

    if not start_param or not end_param:
        messages.error(request, "Please select both start and end dates.")
        return render(request, "home.html", context)

    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return render(request, "home.html", context)

    pickup_location = (
        Location.objects.filter(pk=pickup_location_id).first()
        if pickup_location_id
        else None
    )
    return_location = (
        Location.objects.filter(pk=return_location_id).first()
        if return_location_id
        else None
    )

    if request.user.is_authenticated:
        my_cart_vehicle_ids = CartItem.objects.filter(
            cart__user_id=request.user.id,
            start_date__lt=end_date,
            end_date__gt=start_date,
        ).values_list("vehicle_id", flat=True)
    else:
        my_cart_vehicle_ids = []

    available_ids = Reservation.available_vehicles(
        start_date, end_date, pickup_location, return_location
    )

    vehicles_qs = Vehicle.objects.filter(id__in=available_ids)
    if request.user.is_authenticated:
        vehicles_qs = vehicles_qs.exclude(id__in=my_cart_vehicle_ids)

    results = []
    for v in vehicles_qs:
        q = quote_total(
            start_date,
            end_date,
            RateTable(day=float(v.price_per_day), currency="EUR"),
        )
        results.append(
            {
                "vehicle": v,
                "quote": {
                    "days": q["days"],
                    "total": q["total"],
                    "currency": q["currency"],
                },
            }
        )
    if results:
        context["results"] = results
        return render(request, "home.html", context)
    return render(request, "home.html", context)
