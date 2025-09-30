from django.contrib import messages
from django.db import models
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render, get_object_or_404

from accounts.views.admins_managers import manager_required
from inventory.models.reservation import Location, ReservationStatus


@login_required
@manager_required
@permission_required("inventory.view_location", raise_exception=True)
def location_list(request):
    """
    List all locations.

    Renders:
        accounts/locations/location_list.html

    Context:
        locations (QuerySet[Location])
    """
    locations = Location.objects.all()
    return render(
        request, "accounts/locations/location_list.html", {"locations": locations}
    )


@login_required
@manager_required
@permission_required("inventory.add_location", raise_exception=True)
def location_create(request):
    """
    Create a new location by name.

    - GET renders a simple form.
    - POST creates a Location when 'name' is supplied; otherwise shows error.

    Renders:
        accounts/locations/location_form.html
    """
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            Location.objects.create(name=name)
            messages.success(request, "Location created.")
            return redirect("accounts:location-list")
        messages.error(request, "Please provide a name.")
    return render(
        request, "accounts/locations/location_form.html", {"title": "Create location"}
    )


@login_required
@manager_required
@permission_required("inventory.change_location", raise_exception=True)
def location_edit(request, pk):
    """
    Edit the name of an existing location.

    Args:
        pk (int): Location primary key.

    Renders:
        accounts/locations/location_form.html
    """
    loc = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            loc.name = name
            loc.save()
            messages.success(request, "Location updated.")
            return redirect("accounts:location-list")
        messages.error(request, "Please provide a name.")
    return render(
        request,
        "accounts/locations/location_form.html",
        {"location": loc, "title": "Edit location"},
    )


@login_required
@manager_required
@permission_required("inventory.delete_location", raise_exception=True)
def location_delete(request, pk):
    """
    Delete a location if it is not referenced by any blocking reservations.

    - Prevents deletion when an ongoing reservation uses the location as pickup
      or return location.
    - On success, deletes and redirects with a success message.

    Args:
        pk (int): Location primary key.

    Redirects:
        accounts:location-list
    """
    loc = get_object_or_404(Location, pk=pk)

    from inventory.models.reservation import VehicleReservation as VR

    has_blocking = (
        VR.objects.filter(group__status__in=ReservationStatus.blocking())
        .filter(models.Q(pickup_location=loc) | models.Q(return_location=loc))
        .exists()
    )

    if has_blocking:
        messages.error(
            request,
            "This location is used by an ongoing reservation and cannot be deleted.",
        )
        return redirect("accounts:location-list")

    loc.delete()
    messages.success(request, "Location deleted successfully.")
    return redirect("accounts:location-list")
