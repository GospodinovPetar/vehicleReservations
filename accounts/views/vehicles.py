from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import redirect, render, get_object_or_404

from accounts.forms import VehicleForm
from accounts.views.admins_managers import manager_required
from inventory.models.reservation import Location, ReservationStatus
from inventory.models.vehicle import Vehicle


@login_required
@manager_required
@permission_required("inventory.view_vehicle", raise_exception=True)
def vehicle_list(request):
    """
    List all vehicles for managers/admins.

    Renders:
        accounts/vehicles/vehicle_list.html

    Context:
        vehicles (QuerySet[Vehicle]): All vehicles.
    """
    vehicles = Vehicle.objects.all()
    return render(
        request, "accounts/vehicles/vehicle_list.html", {"vehicles": vehicles}
    )


@login_required
@manager_required
@permission_required("inventory.add_vehicle", raise_exception=True)
def vehicle_create(request):
    """
    Create a new vehicle.

    - If a `pickup` GET param is provided and valid, pre-selects that location.
    - On POST with valid data, saves the vehicle, stores the last chosen pickup
      in the session, flashes a success message, and redirects to the list.
    - On validation errors, flashes an error message and re-renders the form.

    Renders:
        accounts/vehicles/vehicle_form.html

    Session:
        last_pickup_id (int|None): The last selected pickup location ID.
    """
    pickup_param = request.GET.get("pickup")

    initial = {}
    if pickup_param:
        try:
            loc = Location.objects.filter(pk=int(pickup_param)).only("id").first()
            if loc:
                initial["available_pickup_locations"] = loc.pk
        except (TypeError, ValueError):
            pass

    form = VehicleForm(request.POST or None, initial=initial, request=request)

    if request.method == "POST":
        if form.is_valid():
            vehicle = form.save()
            last_pickup = form.cleaned_data.get("available_pickup_locations")
            request.session["last_pickup_id"] = getattr(last_pickup, "pk", None)
            messages.success(request, "Vehicle created successfully.")
            return redirect("accounts:vehicle-list")
        messages.error(request, "Please fix the errors below.")

    return render(request, "accounts/vehicles/vehicle_form.html", {"form": form})


@login_required
@manager_required
@permission_required("inventory.change_vehicle", raise_exception=True)
def vehicle_edit(request, pk):
    """
    Edit an existing vehicle.

    - On GET, displays a form populated with the vehicle.
    - On POST with valid data, updates vehicle and its pickup/return locations,
      flashes a success message, and redirects to the list.

    Args:
        pk (int): Vehicle primary key.

    Renders:
        accounts/vehicles/vehicle_form.html
    """
    vehicle = get_object_or_404(Vehicle, pk=pk)

    if request.method == "POST":
        form = VehicleForm(request.POST, instance=vehicle)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.save()

            pickup = form.cleaned_data.get("available_pickup_locations")
            if pickup:
                vehicle.available_pickup_locations.set([pickup])
            else:
                vehicle.available_pickup_locations.clear()

            dropoffs = form.cleaned_data.get("available_return_locations")
            if dropoffs:
                vehicle.available_return_locations.set(dropoffs)
            else:
                vehicle.available_return_locations.clear()

            messages.success(request, "Vehicle updated successfully.")
            return redirect("accounts:vehicle-list")
    else:
        form = VehicleForm(instance=vehicle)

    return render(
        request,
        "accounts/vehicles/vehicle_form.html",
        {"form": form},
    )


@login_required
@manager_required
@permission_required("inventory.delete_vehicle", raise_exception=True)
def vehicle_delete(request, pk):
    """
    Delete a vehicle if it is not part of any blocking reservation.

    - If the vehicle has an ongoing (blocking) reservation, blocks deletion and
      flashes an error.
    - Otherwise deletes the vehicle, flashes success, and redirects to the list.

    Args:
        pk (int): Vehicle primary key.

    Redirects:
        accounts:vehicle-list
    """
    vehicle = get_object_or_404(Vehicle, pk=pk)

    if vehicle.reservations.filter(
        group__status__in=ReservationStatus.blocking()
    ).exists():
        messages.error(
            request,
            "This vehicle is part of an ongoing reservation and cannot be deleted.",
        )
        return redirect("accounts:vehicle-list")

    vehicle.delete()
    messages.success(request, "Vehicle deleted successfully.")
    return redirect("accounts:vehicle-list")
