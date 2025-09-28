from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date

from cart.models.cart import CartItem
from inventory.helpers.pricing import RateTable, quote_total
from inventory.models.reservation import Location, ReservationStatus, VehicleReservation
from inventory.models.vehicle import Vehicle


def home(request: HttpRequest) -> HttpResponse:
    locations_qs = Location.objects.all()
    context = {"locations": locations_qs}
    return render(request, "home.html", context)


def _clip(
    a: date, b: date, lo: date, hi: date
) -> Tuple[Optional[date], Optional[date]]:
    start_value = a if a >= lo else lo
    end_value = b if b <= hi else hi
    if start_value < end_value:
        return start_value, end_value
    return None, None


def _merge(blocks: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    if not blocks:
        return []
    sorted_blocks = sorted(blocks, key=lambda pair: pair[0])
    merged: List[Tuple[date, date]] = [sorted_blocks[0]]
    for start_value, end_value in sorted_blocks[1:]:
        prev_start, prev_end = merged[-1]
        if start_value <= prev_end:
            new_end = prev_end if prev_end >= end_value else end_value
            merged[-1] = (prev_start, new_end)
        else:
            merged.append((start_value, end_value))
    return merged


def _free_slices(
    search_start: date, search_end: date, blocks: List[Tuple[date, date]]
) -> List[Tuple[date, date]]:
    clipped: List[Tuple[date, date]] = []
    for block_start, block_end in blocks:
        c_start, c_end = _clip(block_start, block_end, search_start, search_end)
        if c_start is not None and c_end is not None:
            clipped.append((c_start, c_end))
    merged = _merge(clipped)
    free_list: List[Tuple[date, date]] = []
    cursor = search_start
    for busy_start, busy_end in merged:
        if cursor < busy_start:
            free_list.append((cursor, busy_start))
        if busy_end > cursor:
            cursor = busy_end
    if cursor < search_end:
        free_list.append((cursor, search_end))
    return free_list


def search(request: HttpRequest) -> HttpResponse:
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

    if start_date is None or end_date is None or not (start_date < end_date):
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
        free_windows = _free_slices(start_date, end_date, vehicle_blocks)
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
