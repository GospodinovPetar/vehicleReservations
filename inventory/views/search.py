from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Tuple

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date

from cart.models.cart import CartItem
from inventory.helpers.intervals import free_slices
from inventory.helpers.pricing import RateTable, quote_total
from inventory.models.reservation import Location, ReservationStatus, VehicleReservation
from inventory.models.vehicle import Vehicle, VehicleType, Gearbox  # <-- added VehicleType


def home(request: HttpRequest) -> HttpResponse:
    """
    Render the home page with a list of locations for the search form,
    plus a simple vehicle filter (name, type, pickup, drop-off).
    """
    locations_qs = Location.objects.all().order_by("name")

    raw_gearbox = (request.GET.get("gearbox") or "").strip().lower()
    selected_gearbox = raw_gearbox if raw_gearbox in {Gearbox.AUTOMATIC, Gearbox.MANUAL} else ""

    context: Dict[str, Any] = {
        "locations": locations_qs,
        "vehicle_types": list(VehicleType.choices),
        "start": (request.GET.get("start") or "").strip(),
        "end": (request.GET.get("end") or "").strip(),
        "pickup_location": (request.GET.get("pickup_location") or "").strip(),
        "return_location": (request.GET.get("return_location") or "").strip(),
        "selected_gearbox": selected_gearbox,
        "results": [],
        "partial_results": [],
    }
    return render(request, "home.html", context)


def search(request: HttpRequest) -> HttpResponse:
    """
    Search vehicles available in a date range with optional filters.
    """
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    pickup_location_param = (request.GET.get("pickup_location") or "").strip()
    return_location_param = (request.GET.get("return_location") or "").strip()

    # Additional filters to align with the vehicle list filter
    name_q = (request.GET.get("name") or "").strip()
    car_type_q = (request.GET.get("car_type") or "").strip()  # dropdown value

    # Gearbox filter
    raw_gearbox = (request.GET.get("gearbox") or "").strip().lower()
    selected_gearbox = raw_gearbox if raw_gearbox in {Gearbox.AUTOMATIC, Gearbox.MANUAL} else ""

    start_date = parse_date(start_str) if start_str else None
    end_date = parse_date(end_str) if end_str else None

    context: Dict[str, Any] = {
        "start": start_str or "",
        "end": end_str or "",
        "pickup_location": pickup_location_param,
        "return_location": return_location_param,
        "locations": Location.objects.all().order_by("name"),
        "vehicle_types": list(VehicleType.choices),
        "selected_gearbox": selected_gearbox,
        "results": [],
        "partial_results": [],
    }

    if not start_str or not end_str:
        messages.error(request, "Please provide both a start date and an end date.")
        return render(request, "home.html", context)

    if start_date is None or end_date is None:
        messages.error(request, "One or both dates are invalid. Use YYYY-MM-DD.")
        return render(request, "home.html", context)

    today = date.today()
    if start_date < today and end_date < today:
        messages.error(request, "Start date and end date cannot be in the past.")
        return render(request, "home.html", context)
    if start_date < today:
        messages.error(request, "Start date cannot be in the past.")
        return render(request, "home.html", context)
    if end_date < today:
        messages.error(request, "End date cannot be in the past.")
        return render(request, "home.html", context)

    if start_date == end_date:
        messages.error(request, "Start date must be before end date (cannot be the same day).")
        return render(request, "home.html", context)
    if start_date > end_date:
        messages.error(request, "Start date must be before end date.")
        return render(request, "home.html", context)

    vehicles_qs = (
        Vehicle.objects.all()
        .prefetch_related("available_pickup_locations", "available_return_locations")
        .filter(
            available_pickup_locations__isnull=False,
            available_return_locations__isnull=False,
        )
        .order_by("id")
    )

    if selected_gearbox:
        vehicles_qs = vehicles_qs.filter(gearbox=selected_gearbox)

    if pickup_location_param and Location.objects.filter(pk=pickup_location_param).exists():
        vehicles_qs = vehicles_qs.filter(available_pickup_locations__id=pickup_location_param)

    if return_location_param and Location.objects.filter(pk=return_location_param).exists():
        vehicles_qs = vehicles_qs.filter(available_return_locations__id=return_location_param)

    if name_q:
        vehicles_qs = vehicles_qs.filter(name__icontains=name_q)
    if car_type_q:
        vehicles_qs = vehicles_qs.filter(car_type=car_type_q)

    vehicles_qs = vehicles_qs.distinct()

    user_id_value = request.user.id if request.user.is_authenticated else None

    reservations_values = VehicleReservation.objects.filter(
        group__status__in=ReservationStatus.blocking(),
        start_date__lt=end_date,
        end_date__gt=start_date,
    ).values("vehicle_id", "start_date", "end_date")

    my_cart_values = CartItem.objects.none()
    if user_id_value is not None:
        my_cart_values = CartItem.objects.filter(
            cart__user_id=user_id_value,
            start_date__lt=end_date,
            end_date__gt=start_date,
        ).values("vehicle_id", "start_date", "end_date")

    blocks_by_vehicle: dict[int, List[Tuple[date, date]]] = defaultdict(list)
    for row in reservations_values:
        blocks_by_vehicle[row["vehicle_id"]].append((row["start_date"], row["end_date"]))
    for row in my_cart_values:
        blocks_by_vehicle[row["vehicle_id"]].append((row["start_date"], row["end_date"]))

    results_list: List[Dict[str, Any]] = []
    partial_results_list: List[Dict[str, Any]] = []

    for vehicle in vehicles_qs:
        vehicle_blocks = blocks_by_vehicle.get(vehicle.id, [])
        free_windows = free_slices(start_date, end_date, vehicle_blocks)
        if not free_windows:
            continue

        rate_table = RateTable(day=float(vehicle.price_per_day), currency="EUR")

        if (
            len(free_windows) == 1
            and free_windows[0][0] == start_date
            and free_windows[0][1] == end_date
        ):
            quote = quote_total(start_date, end_date, rate_table)
            results_list.append(
                {
                    "vehicle": vehicle,
                    "quote": {
                        "days": quote["days"],
                        "total": quote["total"],
                        "currency": quote["currency"],
                    },
                }
            )
        else:
            slices_list: List[Dict[str, Any]] = []
            for slice_start, slice_end in free_windows:
                quote = quote_total(slice_start, slice_end, rate_table)
                slices_list.append(
                    {
                        "start": slice_start,
                        "end": slice_end,
                        "quote": {
                            "days": quote["days"],
                            "total": quote["total"],
                            "currency": quote["currency"],
                        },
                    }
                )
            partial_results_list.append({"vehicle": vehicle, "slices": slices_list})

    context["results"] = results_list
    context["partial_results"] = partial_results_list

    return render(request, "home.html", context)
