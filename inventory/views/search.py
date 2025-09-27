from datetime import date
from typing import List, Tuple
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.dateparse import parse_date

from cart.models.cart import CartItem
from inventory.helpers.pricing import quote_total, RateTable
from inventory.models.reservation import VehicleReservation, Location, ReservationStatus
from inventory.models.vehicle import Vehicle


def home(request):
    locations = Location.objects.all()
    context = {"locations": locations}
    return render(request, "home.html", context)


def _clip(a: date, b: date, lo: date, hi: date):
    s = max(a, lo)
    e = min(b, hi)
    return (s, e) if s < e else (None, None)


def _merge(blocks: List[tuple]):
    if not blocks:
        return []
    blocks = sorted(blocks, key=lambda x: x[0])
    merged = [blocks[0]]
    for s, e in blocks[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def _free_slices(search_start: date, search_end: date, blocks: List[tuple]):
    clipped = []
    for s, e in blocks:
        cs, ce = _clip(s, e, search_start, search_end)
        if cs and ce:
            clipped.append((cs, ce))
    merged = _merge(clipped)
    free: List[tuple] = []
    cur = search_start
    for bs, be in merged:
        if cur < bs:
            free.append((cur, bs))
        cur = max(cur, be)
    if cur < search_end:
        free.append((cur, search_end))
    return free


def search(request):
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    pickup_location = (request.GET.get("pickup_location") or "").strip()
    return_location = (request.GET.get("return_location") or "").strip()

    start_date = parse_date(start_str) if start_str else None
    end_date = parse_date(end_str) if end_str else None

    context = {
        "start": start_str or "",
        "end": end_str or "",
        "pickup_location": pickup_location,
        "return_location": return_location,
        "locations": Location.objects.all().order_by("name"),
        "results": [],
        "partial_results": [],
    }

    if not (start_date and end_date and start_date < end_date):
        return render(request, "home.html", context)

    vehicles_qs = (
        Vehicle.objects.all()
        .prefetch_related("available_pickup_locations", "available_return_locations")
        .order_by("id")
    )

    if pickup_location and Location.objects.filter(pk=pickup_location).exists():
        vehicles_qs = vehicles_qs.filter(available_pickup_locations__id=pickup_location)

    if return_location and Location.objects.filter(pk=return_location).exists():
        vehicles_qs = vehicles_qs.filter(available_return_locations__id=return_location)

    vehicles_qs = vehicles_qs.distinct()

    my_id = request.user.id if request.user.is_authenticated else None

    res_qs = (
        VehicleReservation.objects.filter(
            group__status__in=ReservationStatus.blocking(),
            start_date__lt=end_date,
            end_date__gt=start_date,
        )
        .values("vehicle_id", "start_date", "end_date")
    )

    my_cart_qs = CartItem.objects.none()
    if my_id:
        my_cart_qs = (
            CartItem.objects.filter(
                cart__user_id=my_id,
                start_date__lt=end_date,
                end_date__gt=start_date,
            )
            .values("vehicle_id", "start_date", "end_date")
        )

    blocks_by_vehicle = defaultdict(list)
    for row in res_qs:
        blocks_by_vehicle[row["vehicle_id"]].append((row["start_date"], row["end_date"]))
    for row in my_cart_qs:
        blocks_by_vehicle[row["vehicle_id"]].append((row["start_date"], row["end_date"]))

    results = []
    partial_results = []

    for v in vehicles_qs:
        blocks = blocks_by_vehicle.get(v.id, [])
        free = _free_slices(start_date, end_date, blocks)
        if not free:
            continue

        rt = RateTable(day=float(v.price_per_day), currency="EUR")

        if len(free) == 1 and free[0][0] == start_date and free[0][1] == end_date:
            q = quote_total(start_date, end_date, rt)
            results.append(
                {
                    "vehicle": v,
                    "quote": {"days": q["days"], "total": q["total"], "currency": q["currency"]},
                }
            )
        else:
            slices = []
            for s, e in free:
                q = quote_total(s, e, rt)
                slices.append(
                    {
                        "start": s,
                        "end": e,
                        "quote": {"days": q["days"], "total": q["total"], "currency": q["currency"]},
                    }
                )
            partial_results.append({"vehicle": v, "slices": slices})

    context["results"] = results
    context["partial_results"] = partial_results

    return render(request, "home.html", context)
