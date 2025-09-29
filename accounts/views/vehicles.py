from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    user_passes_test,
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
    vehicles = Vehicle.objects.all()
    return render(
        request, "accounts/vehicles/vehicle_list.html", {"vehicles": vehicles}
    )


@login_required
@manager_required
@permission_required("inventory.add_vehicle", raise_exception=True)
def vehicle_create(request):
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
