from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Vehicle, Location, Reservation, ReservationStatus
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes
from accounts.models import CustomUser


# -----------------------------
# Helpers
# -----------------------------
def parse_iso_date(value):
    """Return a date from YYYY-MM-DD string or None on error."""
    try:
        if value:
            return date.fromisoformat(value)
        return None
    except Exception:
        return None


def compute_total(days_count, price_per_day):
    """Pricing: total = days × daily price."""
    if price_per_day is None:
        return Decimal("0.00")
    daily = Decimal(str(price_per_day))
    total = daily * Decimal(int(days_count))
    return total.quantize(Decimal("0.01"))


# -----------------------------
# Views
# -----------------------------
def home(request):
    locations_qs = Location.objects.all()
    context = {"locations": locations_qs}
    return render(request, "home.html", context)


def search(request):
    start_param = request.GET.get("start")
    end_param = request.GET.get("end")
    pickup_location_id = request.GET.get("pickup_location")
    return_location_id = request.GET.get("return_location")

    locations_qs = Location.objects.all()
    context = {
        "locations": locations_qs,
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

    # optional location filters
    pickup_location = None
    if pickup_location_id:
        pickup_location = Location.objects.filter(id=pickup_location_id).first()

    return_location = None
    if return_location_id:
        return_location = Location.objects.filter(id=return_location_id).first()

    # available vehicles for that window (and locations if provided)
    available_ids_qs = Reservation.available_vehicles(
        start_date, end_date, pickup_location, return_location
    )
    vehicles_qs = Vehicle.objects.filter(id__in=available_ids_qs)

    # build a plain list of results
    results = []
    days_count = (end_date - start_date).days
    for v in vehicles_qs:
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

        available_ids_qs = Reservation.available_vehicles(
            start_date, end_date, pickup_location, return_location
        )

        vehicles_qs = Vehicle.objects.filter(id__in=available_ids_qs).prefetch_related(
            "available_pickup_locations", "available_return_locations"
        )

    context["results"] = results
    return render(request, "home.html", context)


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

    # Try posted IDs first
    pickup_location = None
    if data.get("pickup_location"):
        pickup_location = get_object_or_404(Location, pk=data.get("pickup_location"))
    else:
        # fall back to first allowed pickup location
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
