from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date

from cart.models.cart import CartItem
from inventory.helpers.intervals import free_slices
from inventory.helpers.pricing import RateTable, quote_total
from inventory.models.reservation import Location, ReservationStatus, VehicleReservation
from inventory.models.vehicle import Vehicle


def home(request: HttpRequest) -> HttpResponse:
    """
    Render the home page with a list of locations for the search form.

    Context:
        locations (QuerySet[Location]): All locations for user selection.

    Returns:
        HttpResponse: Rendered "home.html".
    """
    locations_qs = Location.objects.all()
    context = {"locations": locations_qs}
    return render(request, "home.html", context)


def search(request: HttpRequest) -> HttpResponse:
    """
    Search vehicles available in a date range with optional location filters.

    Query params:
        start (YYYY-MM-DD): Start date (required with `end`).
        end (YYYY-MM-DD): End date (must be after `start`).
        pickup_location: Optional Location PK to restrict pickups.
        return_location: Optional Location PK to restrict returns.

    Behavior:
        - Validates dates; if invalid, re-renders the home page with existing inputs.
        - Filters vehicles that have both pickup and return locations configured,
          optionally constrained by the selected locations.
        - Computes blocking intervals from confirmed reservations and the user's cart.
        - Uses `free_slices` to find available windows within the requested range.
        - Produces:
            * `results`: vehicles fully available for the whole period, with a quote.
            * `partial_results`: vehicles available only for sub-windows, each quoted.

    Returns:
        HttpResponse: Rendered "home.html" with results and partial_results.
    """
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    pickup_location_param = (request.GET.get("pickup_location") or "").strip()
    return_location_param = (request.GET.get("return_location") or "").strip()

    start_date = parse_date(start_str) if start_str else None
    end_date = parse_date(end_str) if end_str else None

    context: Dict[str, Any] = {
        "start": start_str or "",
        "end": end_str or "",
        "pickup_location": pickup_location_param,
        "return_location": return_location_param,
        "locations": Location.objects.all().order_by("name"),
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

    start_in_past = start_date < today
    end_in_past = end_date < today
    if start_in_past and end_in_past:
        messages.error(request, "Start date and end date cannot be in the past.")
        return render(request, "home.html", context)
    if start_in_past:
        messages.error(request, "Start date cannot be in the past.")
        return render(request, "home.html", context)
    if end_in_past:
        messages.error(request, "End date cannot be in the past.")
        return render(request, "home.html", context)

    # Order check
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

    if (
        pickup_location_param
        and Location.objects.filter(pk=pickup_location_param).exists()
    ):
        vehicles_qs = vehicles_qs.filter(
            available_pickup_locations__id=pickup_location_param
        )

    if (
        return_location_param
        and Location.objects.filter(pk=return_location_param).exists()
    ):
        vehicles_qs = vehicles_qs.filter(
            available_return_locations__id=return_location_param
        )

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
        vid = row["vehicle_id"]
        s = row["start_date"]
        e = row["end_date"]
        blocks_by_vehicle[vid].append((s, e))
    for row in my_cart_values:
        vid = row["vehicle_id"]
        s = row["start_date"]
        e = row["end_date"]
        blocks_by_vehicle[vid].append((s, e))

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
