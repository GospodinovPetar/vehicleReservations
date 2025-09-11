from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from inventory.models import Reservation, Location, Vehicle, ReservationStatus
from .forms import CustomUserCreationForm
from django.contrib.auth.decorators import user_passes_test, login_required


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
    """
    Pricing:
    total = days_count * price_per_day
    """
    if price_per_day is None:
        return Decimal("0.00")
    daily = Decimal(str(price_per_day))
    total = daily * Decimal(int(days_count))
    return total.quantize(Decimal("0.01"))


# -----------------------------
# Views
# -----------------------------
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

    # optional location filters
    pickup_location = None
    if pickup_location_id:
        pickup_location = Location.objects.filter(id=pickup_location_id).first()

    return_location = None
    if return_location_id:
        return_location = Location.objects.filter(id=return_location_id).first()

    # find available vehicles for that window (and locations if provided)
    available_ids = Reservation.available_vehicles(
        start_date, end_date, pickup_location, return_location
    )
    vehicles = Vehicle.objects.filter(id__in=available_ids)

    # build a plain list of results (no comprehensions)
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


@login_required
@require_http_methods(["POST"])
def reserve(request):
    """
    Create a reservation:
    - require vehicle, pickup_location, return_location
    - require valid date range
    - model save() computes price automatically
    """
    data = request.POST

    vehicle_id = data.get("vehicle")
    pickup_location_id = data.get("pickup_location")
    return_location_id = data.get("return_location")
    start_param = data.get("start")
    end_param = data.get("end")

    if not vehicle_id or not pickup_location_id or not return_location_id:
        messages.error(request, "Please choose a vehicle, pickup and return locations.")
        return redirect("/")

    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    pickup_location = get_object_or_404(Location, id=pickup_location_id)
    return_location = get_object_or_404(Location, id=return_location_id)

    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return redirect(f"/search/?start={start_param or ''}&end={end_param or ''}")

    # create reservation; model clean() will check availability and locations
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
        return redirect(f"/search/?start={start_param or ''}&end={end_param or ''}")

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
    """
    Allow rejecting only if currently 'reserved' or 'awaiting pickup'.
    """
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


# -------- auth views --------


@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            login(request, new_user)
            messages.success(
                request, "Your account was created and you are now logged in."
            )
            return redirect("/")
        messages.error(request, "Please correct the errors below.")
    else:
        form = CustomUserCreationForm()
    return render(request, "auth.html", {"form": form, "title": "Register"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            user = form.get_user()

            # TODO (BooleanField in the database showing permissions)
            # Otherwise getting Unresolved attribute reference 'is_superuser' for class 'AbstractBaseUser'
            # And skips the if statements and goes directly to normal user
            # Role-based redirect

            if user.is_superuser:
                return redirect("accounts:admin-dashboard")
            elif user.role == "manager":
                return redirect("accounts:manager-dashboard")
            else:  # normal user
                return redirect("/")

        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)

    return render(request, "auth.html", {"form": form, "title": "Login"})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_superuser)(view_func)


@superuser_required
def admin_dashboard(request):
    return render(request, "accounts/admin_dashboard.html")


def manager_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.role == "manager")(view_func)


@manager_required
def manager_dashboard(request):
    return render(request, "accounts/manager_dashboard.html")
