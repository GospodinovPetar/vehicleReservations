from collections import defaultdict
from typing import Dict, List

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import render

from inventory.helpers.intervals import _free_slices
from inventory.models.cart import CartItem
from inventory.models.reservation import Location, Reservation, ReservationStatus
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

    pickup_location = Location.objects.filter(pk=pickup_location_id).first() if pickup_location_id else None
    return_location = Location.objects.filter(pk=return_location_id).first() if return_location_id else None

    allowed_qs = Vehicle.objects.all()
    if pickup_location is not None:
        allowed_qs = allowed_qs.annotate(_pc=Count("available_pickup_locations", distinct=True)) \
                               .filter(Q(_pc=0) | Q(available_pickup_locations=pickup_location))
    if return_location is not None:
        allowed_qs = allowed_qs.annotate(_rc=Count("available_return_locations", distinct=True)) \
                               .filter(Q(_rc=0) | Q(available_return_locations=return_location))

    # Fully available
    available_ids = Reservation.available_vehicles(start_date, end_date, pickup_location, return_location)
    fully_available_qs = allowed_qs.filter(id__in=available_ids)

    if request.user.is_authenticated:
        my_cart_vehicle_ids = CartItem.objects.filter(
            cart__user_id=request.user.id,
            start_date__lt=end_date,
            end_date__gt=start_date,
        ).values_list("vehicle_id", flat=True)
        fully_available_qs = fully_available_qs.exclude(id__in=my_cart_vehicle_ids)
    else:
        my_cart_vehicle_ids = []

    results = []
    for v in fully_available_qs.order_by("name"):
        q = quote_total(start_date, end_date, RateTable(day=float(v.price_per_day), currency="EUR"))
        results.append({"vehicle": v, "quote": q})

    # Partially available
    partial_candidates_qs = allowed_qs.exclude(id__in=available_ids)

    conflicts = Reservation.objects.filter(
        vehicle_id__in=partial_candidates_qs.values_list("id", flat=True),
        status__in=ReservationStatus.blocking(),
        start_date__lt=end_date,
        end_date__gt=start_date,
    ).values("vehicle_id", "start_date", "end_date")

    # Group conflicts per vehicle_id
    busy_map: Dict[int, List[tuple]] = defaultdict(list)
    for row in conflicts:
        busy_map[row["vehicle_id"]].append((row["start_date"], row["end_date"]))

    partial_results = []
    partial_qs = partial_candidates_qs
    if request.user.is_authenticated and my_cart_vehicle_ids:
        partial_qs = partial_qs.exclude(id__in=my_cart_vehicle_ids)

    for v in partial_qs.order_by("name"):
        slices = _free_slices(start_date, end_date, busy_map.get(v.id, []))
        useful = [(a, b) for (a, b) in slices if a < b]
        if not useful:
            continue

        priced_slices = []
        for a, b in useful:
            q = quote_total(a, b, RateTable(day=float(v.price_per_day), currency="EUR"))
            priced_slices.append({"start": a, "end": b, "quote": q})

        partial_results.append({"vehicle": v, "slices": priced_slices})

    context["results"] = results
    context["partial_results"] = partial_results
    return render(request, "home.html", context)
