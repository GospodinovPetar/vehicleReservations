from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.redirect_back_to_search import redirect_back_to_search
from inventory.models.reservation import (
    Location,
    VehicleReservation,
    ReservationStatus,
    ReservationGroup,
)
from inventory.models.vehicle import Vehicle
from mockpay.models import PaymentIntent, PaymentIntentStatus


@login_required
@require_http_methods(["POST"])
def reserve(request: HttpRequest) -> HttpResponse:
    form_data = request.POST

    vehicle_param = form_data.get("vehicle")
    start_param = form_data.get("start")
    end_param = form_data.get("end")
    pickup_param = form_data.get("pickup_location")
    return_param = form_data.get("return_location")

    vehicle_obj = get_object_or_404(Vehicle, pk=vehicle_param)

    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return redirect_back_to_search(start_param, end_param)

    if pickup_param:
        pickup_location_obj = get_object_or_404(Location, pk=pickup_param)
    else:
        pickup_location_obj = vehicle_obj.available_pickup_locations.first()

    if return_param:
        return_location_obj = get_object_or_404(Location, pk=return_param)
    else:
        return_location_obj = vehicle_obj.available_return_locations.first()

    if pickup_location_obj is None or return_location_obj is None:
        messages.error(
            request, "This vehicle has no configured pickup/return locations."
        )
        return redirect_back_to_search(start_param, end_param)

    pickup_allowed = vehicle_obj.available_pickup_locations.filter(
        pk=getattr(pickup_location_obj, "pk", None)
    ).exists()
    if not pickup_allowed:
        messages.error(
            request, "Selected pickup location is not available for this vehicle."
        )
        return redirect_back_to_search(start_param, end_param)

    return_allowed = vehicle_obj.available_return_locations.filter(
        pk=getattr(return_location_obj, "pk", None)
    ).exists()
    if not return_allowed:
        messages.error(
            request, "Selected return location is not available for this vehicle."
        )
        return redirect_back_to_search(start_param, end_param)

    try:
        with transaction.atomic():
            awaiting_group = (
                ReservationGroup.objects.select_for_update()
                .filter(user=request.user, status=ReservationStatus.AWAITING_PAYMENT)
                .order_by("-created_at")
                .first()
            )
            pending_group = None
            if awaiting_group is None:
                pending_group = (
                    ReservationGroup.objects.select_for_update()
                    .filter(user=request.user, status=ReservationStatus.PENDING)
                    .order_by("-created_at")
                    .first()
                )

            if awaiting_group is not None:
                group_obj = awaiting_group
            elif pending_group is not None:
                group_obj = pending_group
            else:
                group_obj = ReservationGroup.objects.create(
                    user=request.user, status=ReservationStatus.PENDING
                )

            if group_obj.status == ReservationStatus.RESERVED:
                messages.error(request, "You can’t modify a reserved reservation.")
                return redirect("inventory:reservations")

            if group_obj.status == ReservationStatus.AWAITING_PAYMENT:
                PaymentIntent.objects.select_for_update().filter(
                    reservation_group=group_obj,
                    status__in=[
                        PaymentIntentStatus.REQUIRES_CONFIRMATION,
                        PaymentIntentStatus.PROCESSING,
                    ],
                ).update(status=PaymentIntentStatus.CANCELED)
                ReservationGroup.objects.filter(pk=group_obj.pk).update(
                    status=ReservationStatus.PENDING
                )
                group_obj.refresh_from_db(fields=["status"])

            reservation_instance = VehicleReservation(
                user=request.user,
                vehicle=vehicle_obj,
                pickup_location=pickup_location_obj,
                return_location=return_location_obj,
                start_date=start_date,
                end_date=end_date,
                group=group_obj,
            )
            reservation_instance.full_clean()
            reservation_instance.save()

            ReservationGroup.objects.filter(pk=group_obj.pk).update(
                status=ReservationStatus.PENDING
            )
            group_obj.refresh_from_db(fields=["status"])

    except Exception as exc:
        messages.error(request, str(exc))
        return redirect_back_to_search(start_param, end_param)

    messages.success(request, "Vehicle added to your reservation.")
    return redirect("inventory:reservations")
