from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods

# Inventory models
from inventory.models.vehicle import Vehicle
from inventory.models.reservation import Reservation, ReservationStatus, Location

from .forms import CustomUserCreationForm, UserEditForm, VehicleForm, ReservationStatusForm

User = get_user_model()


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

            # Blocked or inactive users cannot log in
            if user.is_blocked or not user.is_active:
                messages.error(
                    request,
                    "Your account has been blocked or is inactive. Please contact support.",
                )
                return redirect("accounts:login")

            # Log the user in
            login(request, user)
            messages.success(request, "You are now logged in.")

            # Redirect based on role
            if user.role == "admin":
                return redirect("accounts:admin-dashboard")
            elif user.role == "manager":
                return redirect("accounts:manager-dashboard")
            else:
                return redirect("accounts:user-reservations")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)

    return render(request, "accounts/auth.html", {"form": form, "title": "Login"})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


# ----------- Admin decorators / views -----------
def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.role == "admin")(
        view_func
    )


@admin_required
def admin_dashboard(request):
    query = request.GET.get("q")
    role_filter = request.GET.get("role")
    status_filter = request.GET.get("status")

    users = User.objects.all().order_by("-date_joined")

    if query:
        users = users.filter(username__icontains=query) | users.filter(
            email__icontains=query
        )
    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter == "blocked":
        users = users.filter(is_blocked=True)
    elif status_filter == "active":
        users = users.filter(is_blocked=False)

    stats = {
        "total": User.objects.count(),
        "admins": User.objects.filter(role="admin").count(),
        "managers": User.objects.filter(role="manager").count(),
        "users": User.objects.filter(role="user").count(),
        "blocked": User.objects.filter(is_blocked=True).count(),
    }

    return render(
        request, "accounts/admin_dashboard.html", {"users": users, "stats": stats}
    )


@admin_required
def block_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    # Strict: do not allow any admin-to-admin actions
    if user.role == "admin":
        messages.error(request, "You cannot block another admin.")
    else:
        user.is_blocked = True
        user.save()
        messages.success(request, f"{user.username} has been blocked.")
    return redirect("accounts:admin-dashboard")


@admin_required
def unblock_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot modify another admin.")
    else:
        user.is_blocked = False
        user.save()
        messages.success(request, f"{user.username} has been unblocked.")
    return redirect("accounts:admin-dashboard")


@admin_required
def promote_manager(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot modify another admin.")
    else:
        user.role = "manager"
        user.save()
        messages.success(request, f"{user.username} is now a manager.")
    return redirect("accounts:admin-dashboard")


@admin_required
def demote_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot modify another admin.")
    else:
        user.role = "user"
        user.save()
        messages.success(request, f"{user.username} is now a regular user.")
    return redirect("accounts:admin-dashboard")


@admin_required
def create_user(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "User created successfully.")
            return redirect("accounts:admin-dashboard")
    else:
        form = CustomUserCreationForm()
    return render(
        request, "accounts/admin_user_form.html", {"form": form, "title": "Create User"}
    )


@admin_required
def edit_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    # Do not allow admin to edit other admins
    if user.role == "admin":
        messages.error(request, "You cannot edit another admin.")
        return redirect("accounts:admin-dashboard")

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            # Save with no password change
            form.save()
            messages.success(request, "User updated successfully.")
            return redirect("accounts:admin-dashboard")
    else:
        form = UserEditForm(instance=user)
    return render(
        request,
        "accounts/admin_user_form.html",
        {"form": form, "title": f"Edit {user.username}"},
    )


@admin_required
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot delete another admin.")
        return redirect("accounts:admin-dashboard")

    if request.method == "POST":
        user.delete()
        messages.success(request, "User deleted successfully.")
        return redirect("accounts:admin-dashboard")
    return render(request, "accounts/admin_user_confirm_delete.html", {"user": user})


# ----------- Manager decorators / views -----------
def manager_required(view_func):
    return user_passes_test(
        lambda u: u.is_authenticated and u.role in ["manager", "admin"],
        login_url="/accounts/login/",
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
    # managers/admins see all reservations
    reservations = Reservation.objects.all().select_related(
        "user", "vehicle", "pickup_location", "return_location"
    )
    return render(
        request, "accounts/reservation_list.html", {"reservations": reservations}
    )


# --- VEHICLE VIEWS ---
@manager_required
def vehicle_list(request):
    vehicles = Vehicle.objects.all()
    return render(request, "accounts/vehicle_list.html", {"vehicles": vehicles})


@manager_required
def vehicle_create(request):
    if request.method == "POST":
        form = VehicleForm(request.POST)
        if form.is_valid():
            vehicle = form.save()
            messages.success(request, "Vehicle created successfully.")
            return redirect("accounts:vehicle-list")
    else:
        form = VehicleForm()
    return render(request, "accounts/vehicle_form.html", {"form": form})


@manager_required
def vehicle_edit(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == "POST":
        form = VehicleForm(request.POST, instance=vehicle)
        if form.is_valid():
            form.save()
            messages.success(request, "Vehicle updated successfully.")
            return redirect("accounts:vehicle-list")
    else:
        form = VehicleForm(instance=vehicle)
    return render(request, "accounts/vehicle_form.html", {"form": form})


@manager_required
def vehicle_delete(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    vehicle.delete()
    messages.success(request, "Vehicle deleted successfully.")
    return redirect("accounts:vehicle-list")


# --- RESERVATION VIEWS ---
@manager_required
def reservation_list(request):
    reservations = Reservation.objects.select_related("vehicle", "user").all()
    return render(
        request, "accounts/reservation_list.html", {"reservations": reservations}
    )


@manager_required
def reservation_update(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    # Only allow managers/admins (decorator already ensures this)
    if request.method == "POST":
        form = ReservationStatusForm(request.POST, instance=reservation)
        if form.is_valid():
            form.save()
            messages.success(request, "Reservation updated.")
            return redirect("accounts:reservation-list")
    else:
        form = ReservationStatusForm(instance=reservation)
    return render(
        request,
        "accounts/reservation_update.html",
        {"reservation": reservation, "form": form},
    )


@manager_required
def reservation_approve(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    reservation.status = ReservationStatus.AWAITING_PICKUP
    reservation.save()
    messages.success(request, "Reservation approved (awaiting pickup).")
    return redirect("accounts:reservation-list")


@manager_required
def reservation_reject(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    reservation.status = ReservationStatus.REJECTED
    reservation.save()
    messages.success(request, "Reservation rejected.")
    return redirect("accounts:reservation-list")


# --- User reservation view (normal users only) ---
@login_required
def user_reservations(request):
    reservations = (
        Reservation.objects.filter(user=request.user)
        .select_related("vehicle", "pickup_location", "return_location")
        .all()
    )
    return render(
        request, "accounts/reservation_list_user.html", {"reservations": reservations}
    )


# --- LOCATION MANAGEMENT (accessible to admin) ---
@admin_required
def location_list(request):
    locations = Location.objects.all()
    return render(request, "accounts/location_list.html", {"locations": locations})


@admin_required
def location_create(request):
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            Location.objects.create(name=name)
            messages.success(request, "Location created.")
            return redirect("accounts:location-list")
        messages.error(request, "Please provide a name.")
    return render(request, "accounts/location_form.html", {"title": "Create location"})


@admin_required
def location_edit(request, pk):
    loc = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            loc.name = name
            loc.save()
            messages.success(request, "Location updated.")
            return redirect("accounts:location-list")
        messages.error(request, "Please provide a name.")
    return render(request, "accounts/location_form.html", {"location": loc, "title": "Edit location"})


@admin_required
def location_delete(request, pk):
    loc = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        loc.delete()
        messages.success(request, "Location deleted.")
        return redirect("accounts:location-list")
    return render(request, "accounts/location_confirm_delete.html", {"location": loc})
