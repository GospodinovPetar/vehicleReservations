from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from inventory.models.reservation import ReservationStatus, ReservationGroup
from inventory.views.reservations.reservation_edit_form import ReservationEditForm


@login_required
def add_vehicle(request: HttpRequest, group_id: int) -> HttpResponse:
    group_obj: ReservationGroup = get_object_or_404(
        ReservationGroup, pk=group_id, user=request.user
    )

    if group_obj.status == ReservationStatus.RESERVED:
        messages.error(request, "You can’t modify a reserved reservation.")
        return redirect("inventory:reservations")

    if request.method == "POST":
        form = ReservationEditForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                reservation_instance = form.save(commit=False)
                reservation_instance.user = request.user
                reservation_instance.group = group_obj
                group_obj.status = ReservationStatus.PENDING
                group_obj.save(update_fields=["status"])
                reservation_instance.save()
            messages.success(
                request, "Vehicle added. The reservation is now pending review."
            )
            return redirect("inventory:reservations")
        return render(
            request, "inventory/add_vehicle.html", {"form": form, "group": group_obj}
        )

    blank_form = ReservationEditForm()
    return render(
        request, "inventory/add_vehicle.html", {"form": blank_form, "group": group_obj}
    )
