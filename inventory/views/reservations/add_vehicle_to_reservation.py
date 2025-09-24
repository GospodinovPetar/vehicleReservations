from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from inventory.models.reservation import ReservationStatus, ReservationGroup
from inventory.views.reservations.reservation_edit_form import ReservationEditForm


@login_required
def add_vehicle(request, group_id: int):
    group = get_object_or_404(ReservationGroup, pk=group_id, user=request.user)

    if group.status == ReservationStatus.RESERVED:
        messages.error(request, "You can’t modify a reserved reservation.")
        return redirect("inventory:reservations")

    if request.method == "POST":
        form = ReservationEditForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                rv = form.save(commit=False)
                rv.user = request.user
                rv.group = group
                rv.status = ReservationStatus.PENDING
                rv.save()

            messages.success(request, "Vehicle added. The reservation is now pending review.")
            return redirect("inventory:reservations")
    else:
        form = ReservationEditForm()

    return render(request, "inventory/add_vehicle.html", {"form": form, "group": group})