from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods
from inventory.models.vehicle import Vehicle
from inventory.models.reservation import Reservation, ReservationStatus, Location

from .forms import CustomUserCreationForm, VehicleForm, ReservationStatusForm


# ----------- Auth views -----------
@require_http_methods(["GET", "POST"])
def register(request):
    """User self-registration (role = user by default)."""
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
    return render(request, "accounts/auth.html", {"form": form, "title": "Register"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Blocked users cannot log in
            if user.is_blocked:
                messages.error(
                    request, "Your account has been blocked. Please contact support."
                )
                return redirect("accounts:login")

            login(request, user)
            next_url = request.GET.get("next") or "/"
            messages.success(request, "You are now logged in.")
            return redirect(next_url)
        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)
    return render(request, "auth.html", {"form": form, "title": "Login"})


def blocked_view(request):
    """Page shown to blocked users after logout."""
    return render(request, "accounts/blocked.html")


def logout_view(request):
    """Logout user."""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


# ----------- Dashboards -----------
def superuser_required(view_func):
    return user_passes_test(
        lambda u: u.is_authenticated and u.is_superuser, login_url="/"
    )(view_func)


@superuser_required
def admin_dashboard(request):
    return render(request, "accounts/admin_dashboard.html")


def manager_required(view_func):
    """
    Restrict access to managers (and admins).
    """
    return user_passes_test(
        lambda u: u.is_authenticated and u.role in ["manager", "admin"],
        login_url="/accounts/login/"
    )(view_func)


@manager_required
def manager_dashboard(request):
    return render(request, "accounts/manager_dashboard.html")


@manager_required
def manager_vehicles(request):
    vehicles = Vehicle.objects.all()
    return render(request, "accounts/manager_vehicles.html", {"vehicles": vehicles})


@manager_required
def manager_reservations(request):
    reservations = Reservation.objects.all()
    return render(request, "accounts/manager_reservations.html", {"reservations": reservations})


# -------Manager Dashboard----------
# VEHICLES
@manager_required
def manager_vehicles(request):
    vehicles = Vehicle.objects.all()
    return render(request, "accounts/manager_vehicles.html", {"vehicles": vehicles})


@manager_required
def vehicle_create(request):
    if request.method == "POST":
        form = VehicleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Vehicle created successfully.")
            return redirect("manager:vehicles")
    else:
        form = VehicleForm()
    return render(request, "accounts/vehicle_form.html", {"form": form, "title": "Add Vehicle"})


@manager_required
def vehicle_edit(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == "POST":
        form = VehicleForm(request.POST, instance=vehicle)
        if form.is_valid():
            form.save()
            messages.success(request, "Vehicle updated successfully.")
            return redirect("manager:vehicles")
    else:
        form = VehicleForm(instance=vehicle)
    return render(request, "accounts/vehicle_form.html", {"form": form, "title": "Edit Vehicle"})


@manager_required
def vehicle_delete(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == "POST":
        vehicle.delete()
        messages.success(request, "Vehicle deleted successfully.")
        return redirect("manager:vehicles")
    return render(request, "accounts/confirm_delete.html", {"object": vehicle, "type": "Vehicle"})


# RESERVATIONS
@manager_required
def manager_reservations(request):
    reservations = Reservation.objects.select_related("user", "vehicle").all()
    return render(request, "accounts/manager_reservations.html", {"reservations": reservations})


@manager_required
def reservation_update(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    if request.method == "POST":
        form = ReservationStatusForm(request.POST, instance=reservation)
        if form.is_valid():
            form.save()
            messages.success(request, "Reservation status updated.")
            return redirect("manager:reservations")
    else:
        form = ReservationStatusForm(instance=reservation)
    return render(request, "accounts/reservation_form.html", {"form": form, "reservation": reservation})
