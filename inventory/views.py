from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Vehicle, Location, Reservation
from .pricing import RateTable, quote_total

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


def build_rate_table_for_vehicle(vehicle):
    """
    Build a RateTable for a vehicle.
    If per-period prices exist on vehicle.prices, use them.
    Otherwise, fall back to price_per_day with simple week/month rules.
    """
    currency_code = getattr(vehicle, "currency", "EUR")

    day_price = None
    week_price = None
    month_price = None

    # Try to read Vehicle.prices if present (period_type: day/week/month)
    if hasattr(vehicle, "prices"):
        try:
            for price_row in vehicle.prices.all():
                period_type = getattr(price_row, "period_type", "")
                amount_value = float(getattr(price_row, "amount", 0) or 0)
                if period_type == "day":
                    day_price = amount_value
                elif period_type == "week":
                    week_price = amount_value
                elif period_type == "month":
                    month_price = amount_value
        except Exception:
            # If anything goes wrong, fall back to price_per_day
            pass

    # Fallback using vehicle.price_per_day if needed
    if day_price is None or week_price is None or month_price is None:
        daily = float(getattr(vehicle, "price_per_day", 0) or 0)
        if day_price is None:
            day_price = daily
        if week_price is None:
            week_price = daily * 6
        if month_price is None:
            month_price = daily * 26

    return RateTable(
        day=day_price, week=week_price, month=month_price, currency=currency_code
    )


# -----------------------------
# Views
# -----------------------------


def home(request):
    all_locations = Location.objects.all()
    context = {"locations": all_locations}
    return render(request, "home.html", context)


def search(request):
    start_param = request.GET.get("start")
    end_param = request.GET.get("end")
    pickup_location_id = request.GET.get("pickup_location")
    return_location_id = request.GET.get("return_location")

    all_locations = Location.objects.all()
    context = {
        "locations": all_locations,
        "start": start_param,
        "end": end_param,
        "pickup_location": pickup_location_id,
        "return_location": return_location_id,
    }

    # Require both dates
    if not start_param or not end_param:
        messages.error(request, "Please select both start and end dates.")
        return render(request, "home.html", context)

    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)

    # Validate date order
    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return render(request, "home.html", context)

    # Selected locations (optional)
    pickup_location = None
    if pickup_location_id:
        pickup_location = Location.objects.filter(id=pickup_location_id).first()

    return_location = None
    if return_location_id:
        return_location = Location.objects.filter(id=return_location_id).first()

    # Available vehicles for period and locations
    available_ids = Reservation.available_vehicle_ids(
        start_date, end_date, pickup_location, return_location
    )
    vehicles_qs = Vehicle.objects.filter(id__in=available_ids)

    # Build result list (no comprehensions)
    results = []
    for vehicle in vehicles_qs:
        rate_table = build_rate_table_for_vehicle(vehicle)
        try:
            vehicle_quote = quote_total(start_date, end_date, rate_table)
        except Exception as exc:
            # If pricing fails, show a simple message and skip this vehicle
            messages.error(request, f"Could not compute quote for {vehicle}: {exc}")
            continue

        item = {
            "vehicle": vehicle,
            "quote": vehicle_quote,
        }
        results.append(item)

    context["results"] = results
    return render(request, "home.html", context)


@login_required
@require_http_methods(["POST"])
def reserve(request):
    form_data = request.POST

    vehicle_id = form_data.get("vehicle")
    pickup_location_id = form_data.get("pickup_location")
    return_location_id = form_data.get("return_location")
    start_param = form_data.get("start")
    end_param = form_data.get("end")

    # Resolve objects
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    # Choose pickup location: provided or default from vehicle availability
    if pickup_location_id:
        pickup_location = get_object_or_404(Location, id=pickup_location_id)
    else:
        vehicle_pickup_link = (
            vehicle.vehicle_locations.filter(can_pickup=True)
            .select_related("location")
            .first()
        )
        if vehicle_pickup_link is None:
            messages.error(request, "No pickup locations available for this vehicle.")
            return redirect("/search/")
        pickup_location = vehicle_pickup_link.location

    if return_location_id:
        return_location = get_object_or_404(Location, id=return_location_id)
    else:
        return_links_qs = vehicle.vehicle_locations.filter(
            can_return=True
        ).select_related("location")
        preferred = return_links_qs.filter(location__is_default_return=True).first()
        if preferred:
            return_location = preferred.location
        else:
            any_return_link = return_links_qs.first()
            if any_return_link is None:
                messages.error(
                    request, "No return locations available for this vehicle."
                )
                return redirect("/search/")
            return_location = any_return_link.location

    # Dates
    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return redirect(f"/search/?start={start_param or ''}&end={end_param or ''}")

    # Create reservation instance and validate
    reservation = Reservation(
        user=request.user,
        vehicle=vehicle,
        pickup_location=pickup_location,
        return_location=return_location,
        start_date=start_date,
        end_date=end_date,
        currency=getattr(vehicle, "currency", "EUR"),
    )

    try:
        reservation.clean()
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect(
            f"/search/?start={start_date.isoformat()}&end={end_date.isoformat()}"
        )

    # Compute price via RateTable + quote_total
    rate_table = build_rate_table_for_vehicle(vehicle)
    try:
        quote_info = quote_total(start_date, end_date, rate_table)
    except Exception as exc:
        messages.error(request, f"Could not compute price: {exc}")
        return redirect(
            f"/search/?start={start_date.isoformat()}&end={end_date.isoformat()}"
        )

    reservation.total_price = Decimal(str(quote_info.get("total", 0)))
    reservation.save()

    messages.success(request, "Reservation created!")
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
def cancel_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, user=request.user)
    if reservation.status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "Cannot cancel this reservation.")
    else:
        reservation.status = "CANCELLED"
        reservation.save(update_fields=["status"])
        messages.success(request, "Reservation cancelled.")
    return redirect("/reservations/")


@login_required
@require_http_methods(["POST"])
def reject_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, user=request.user)
    if reservation.status != "PENDING":
        messages.error(request, "Only pending reservations can be rejected.")
    else:
        reservation.status = "REJECTED"
        reservation.save(update_fields=["status"])
        messages.success(request, "Reservation rejected.")
    return redirect("/reservations/")


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            login(request, new_user)
            return redirect("/")
        messages.error(request, "Please correct the errors below.")
    else:
        form = UserCreationForm()
    return render(request, "auth.html", {"form": form, "title": "Register"})


def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.GET.get("next")
            if not next_url:
                next_url = "/"
            return redirect(next_url)
        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)
    return render(request, "auth.html", {"form": form, "title": "Login"})


def logout_view(request):
    logout(request)
    return redirect("/")
