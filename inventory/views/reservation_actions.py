from __future__ import annotations

from django.utils import timezone
from typing import Dict, Any, List

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from config import settings
from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.redirect_back_to_search import redirect_back_to_search
from inventory.models.reservation import (
    Location,
    VehicleReservation,
    ReservationStatus,
    ReservationGroup,
)
from inventory.models.vehicle import Vehicle
from inventory.views.status_switch import transition_group, TransitionError
from mockpay.models import PaymentIntent, PaymentIntentStatus


@login_required
@require_http_methods(["POST"])
def reserve(request: HttpRequest) -> HttpResponse:
    """
    Add a selected vehicle and period to the user's active reservation group.

    Behavior:
        - Validates start/end dates and pickup/return locations (or falls back
          to the vehicle's first allowed locations if not provided).
        - Ensures chosen locations are allowed for the vehicle.
        - Reuses the latest AWAITING_PAYMENT or PENDING group, or creates a new one.
        - If the group is AWAITING_PAYMENT, cancels in-flight payment intents and
          moves the group back to PENDING before adding an item.
        - On success, adds a VehicleReservation and ensures the group is PENDING.

    Returns:
        HttpResponse: Redirects to reservations list on success, or back to search with
        an error message on failure.
    """
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


class ReservationEditForm(forms.ModelForm):
    """Form for editing a reservation's key fields (vehicle, locations, dates)."""

    class Meta:
        """Model binding and widgets for date inputs."""
        model = VehicleReservation
        fields = [
            "vehicle",
            "pickup_location",
            "return_location",
            "start_date",
            "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


@login_required
def my_reservations(request: HttpRequest) -> HttpResponse:
    """
    List the current user's reservation groups, split into active and archived.

    Active excludes REJECTED and CANCELED; both lists prefetch the group's
    reservations with common relations for efficient rendering.

    Returns:
        HttpResponse: Rendered reservations page.
    """
    archived_statuses = [ReservationStatus.REJECTED, ReservationStatus.CANCELED]

    items_queryset = VehicleReservation.objects.select_related(
        "vehicle", "pickup_location", "return_location"
    ).order_by("-start_date")
    items_prefetch = Prefetch("reservations", queryset=items_queryset)

    base_groups = ReservationGroup.objects.filter(user=request.user)

    groups = (
        base_groups.exclude(status__in=archived_statuses)
        .prefetch_related(items_prefetch)
        .order_by("-created_at")
    )

    archived = (
        base_groups.filter(status__in=archived_statuses)
        .prefetch_related(items_prefetch)
        .order_by("-created_at")
    )

    context = {"groups": groups, "archived": archived}
    return render(request, "inventory/reservations.html", context)


@user_passes_test(lambda u: bool(getattr(u, "is_staff", False)))  # TODO REMOVE LAMBDA
@require_http_methods(["POST"])
def approve_group(request: HttpRequest, group_id: int) -> HttpResponse:
    """
    Staff-only: move a reservation group from PENDING to AWAITING_PAYMENT.

    Uses `transition_group` to perform a validated status change.

    Args:
        group_id: Primary key of the ReservationGroup.

    Returns:
        HttpResponse: Redirect back to the reservations page with a status message.
    """
    try:
        group = transition_group(
            group_id=group_id, action="approve", actor=request.user
        )
    except TransitionError as exc:
        messages.info(request, str(exc))
    except Exception as exc:
        messages.error(request, str(exc))
    else:
        reference_value = getattr(group, "reference", None) or str(
            getattr(group, "pk", "")
        )
        messages.success(
            request, f"Reservation {reference_value} approved. Awaiting payment."
        )
    return redirect("inventory:reservations")


@login_required
@require_http_methods(["POST"])
def cancel_reservation(request: HttpRequest, group_id: int) -> HttpResponse:
    """
    Cancel a user's reservation group (if allowed by current status).

    Args:
        group_id: ReservationGroup primary key.

    Returns:
        HttpResponse: Redirect back to reservations with a message.
    """
    try:
        group = transition_group(group_id=group_id, action="cancel", actor=request.user)
    except TransitionError as exc:
        messages.info(request, str(exc))
    except Exception as exc:
        messages.error(request, str(exc))
    else:
        reference_value = getattr(group, "reference", None) or str(
            getattr(group, "pk", "")
        )
        messages.info(request, f"Reservation {reference_value} canceled.")
    return redirect("inventory:reservations")


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_reservation(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Remove a vehicle from a reservation group (not allowed if it's the only one).

    Rules:
        - Disallow edits for groups in REJECTED, CANCELED, or RESERVED.
        - Require that at least one other VehicleReservation remains.
        - Cancel in-flight PaymentIntents for the group.

    Args:
        pk: Primary key of the VehicleReservation to remove.

    Returns:
        HttpResponse: Redirects back to reservations with a status message.
    """
    reservation_obj = get_object_or_404(
        VehicleReservation.objects.select_related("group"),
        pk=pk,
        user=request.user,
    )

    group_obj = reservation_obj.group
    if group_obj is None:
        messages.error(
            request, "You cannot remove the only vehicle in this reservation."
        )
        return redirect("inventory:reservations")

    group_obj = ReservationGroup.objects.select_for_update().get(pk=group_obj.pk)

    canceled_value = getattr(ReservationStatus, "CANCELED", "CANCELED")
    non_editable_statuses = [
        ReservationStatus.REJECTED,
        canceled_value,
        ReservationStatus.RESERVED,
    ]
    if group_obj.status in non_editable_statuses:
        messages.error(request, "This reservation cannot be modified.")
        return redirect("inventory:reservations")

    total_in_group = VehicleReservation.objects.filter(group=group_obj).count()
    if total_in_group <= 1:
        messages.error(
            request, "You cannot remove the only vehicle in this reservation."
        )
        return redirect("inventory:reservations")

    reservation_obj.delete()

    intents_qs = PaymentIntent.objects.select_for_update().filter(
        reservation_group=group_obj,
        status__in=[
            PaymentIntentStatus.REQUIRES_CONFIRMATION,
            PaymentIntentStatus.PROCESSING,
        ],
    )
    for intent in intents_qs:
        intent.status = PaymentIntentStatus.CANCELED
        intent.save(update_fields=["status"])

    messages.success(request, "Vehicle removed from reservation.")
    return redirect("inventory:reservations")


@login_required
@require_http_methods(["GET", "POST"])
def edit_reservation(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Edit a reservation's vehicle, locations, and dates (role-aware access).

    - Admin/Manager may edit any reservation; regular users may edit only their own.
    - Validates date logic and location allowances against the selected vehicle.
    - Prevents overlapping with blocking reservations.
    - Marks the group PENDING when important fields change.
    - Optionally emails the user a change summary.

    Args:
        pk: VehicleReservation primary key.

    Returns:
        HttpResponse: Rendered form on GET/validation errors; redirect on success.
    """
    qs = VehicleReservation.objects.select_related("vehicle", "group", "user")
    user_role = getattr(request.user, "role", "")
    if user_role in ("manager", "admin"):
        reservation_obj = get_object_or_404(qs, pk=pk)
    else:
        reservation_obj = get_object_or_404(qs.filter(user=request.user), pk=pk)

    if request.method == "POST":
        form = ReservationEditForm(request.POST, instance=reservation_obj)

        if form.is_valid():
            selected_vehicle = form.cleaned_data.get("vehicle")
            selected_pickup = form.cleaned_data.get("pickup_location")
            selected_return = form.cleaned_data.get("return_location")
            new_start = form.cleaned_data.get("start_date")
            new_end = form.cleaned_data.get("end_date")

            original_start = reservation_obj.start_date
            original_end = reservation_obj.end_date

            has_date_error = False
            if new_start is None or new_end is None:
                form.add_error(None, "Please provide both pickup and return dates.")
                has_date_error = True
            else:
                if new_start >= new_end:
                    form.add_error("end_date", "End date must be after start date.")
                    has_date_error = True
                today_value = timezone.localdate()
                if new_start < today_value:
                    form.add_error("start_date", "Pickup date cannot be in the past.")
                    has_date_error = True
                if new_end < today_value:
                    form.add_error("end_date", "Return date cannot be in the past.")
                    has_date_error = True

            has_location_error = False
            if selected_vehicle is not None and selected_pickup is not None:
                if selected_vehicle.available_pickup_locations.exists():
                    pickup_allowed = selected_vehicle.available_pickup_locations.filter(
                        pk=selected_pickup.pk
                    ).exists()
                    if not pickup_allowed:
                        form.add_error(
                            "pickup_location",
                            "Pickup location not allowed for this vehicle.",
                        )
                        has_location_error = True

            if selected_vehicle is not None and selected_return is not None:
                if selected_vehicle.available_return_locations.exists():
                    return_allowed = selected_vehicle.available_return_locations.filter(
                        pk=selected_return.pk
                    ).exists()
                    if not return_allowed:
                        form.add_error(
                            "return_location",
                            "Return location not allowed for this vehicle.",
                        )
                        has_location_error = True

            if form.errors or has_date_error or has_location_error:
                vehicles_qs = Vehicle.objects.all().order_by("name")
                locations_qs = Location.objects.all().order_by("name")
                return render(
                    request,
                    "inventory/edit_reservation.html",
                    {
                        "form": form,
                        "reservation": reservation_obj,
                        "vehicles": vehicles_qs,
                        "locations": locations_qs,
                    },
                )

            overlaps_qs = VehicleReservation.objects.filter(
                vehicle_id=(
                    selected_vehicle.pk if selected_vehicle is not None else None
                ),
                group__status__in=ReservationStatus.blocking(),
                start_date__lt=new_end,
                end_date__gt=new_start,
            ).exclude(pk=reservation_obj.pk)
            if overlaps_qs.exists():
                form.add_error(
                    "start_date",
                    "This vehicle is not available in the selected period.",
                )
                vehicles_qs = Vehicle.objects.all().order_by("name")
                locations_qs = Location.objects.all().order_by("name")
                return render(
                    request,
                    "inventory/edit_reservation.html",
                    {
                        "form": form,
                        "reservation": reservation_obj,
                        "vehicles": vehicles_qs,
                        "locations": locations_qs,
                    },
                )

            try:
                with transaction.atomic():
                    before_snapshot: Dict[str, Any] = {
                        "vehicle": reservation_obj.vehicle,
                        "pickup_location": reservation_obj.pickup_location,
                        "return_location": reservation_obj.return_location,
                        "start_date": reservation_obj.start_date,
                        "end_date": reservation_obj.end_date,
                    }

                    instance = form.save(commit=False)
                    instance.full_clean()
                    instance.save()

                    important_fields = {
                        "vehicle",
                        "pickup_location",
                        "return_location",
                        "start_date",
                        "end_date",
                    }
                    changed_fields = set(form.changed_data).intersection(
                        important_fields
                    )
                    important_changed = len(changed_fields) > 0

                    if important_changed and instance.group_id:
                        instance.group.status = ReservationStatus.PENDING
                        instance.group.save(update_fields=["status"])

                    should_email = (
                        important_changed
                        and bool(getattr(instance, "user", None))
                        and bool(getattr(instance.user, "email", ""))
                    )
                    if should_email:
                        after_snapshot: Dict[str, Any] = {
                            "vehicle": instance.vehicle,
                            "pickup_location": instance.pickup_location,
                            "return_location": instance.return_location,
                            "start_date": instance.start_date,
                            "end_date": instance.end_date,
                        }

                        label_map = {
                            "vehicle": "Vehicle",
                            "pickup_location": "Pickup location",
                            "return_location": "Return location",
                            "start_date": "Start date",
                            "end_date": "End date",
                        }

                        def format_value(value: Any, field_name: str) -> str:
                            if field_name in ("start_date", "end_date") and value:
                                try:
                                    return value.strftime("%Y-%m-%d")
                                except Exception:
                                    return str(value)
                            return str(value) if value is not None else "-"

                        changes_payload: List[Dict[str, str]] = []
                        for fname in [
                            "vehicle",
                            "pickup_location",
                            "return_location",
                            "start_date",
                            "end_date",
                        ]:
                            if fname in changed_fields:
                                before_val = before_snapshot.get(fname)
                                after_val = after_snapshot.get(fname)
                                changes_payload.append(
                                    {
                                        "label": label_map[fname],
                                        "before": format_value(before_val, fname),
                                        "after": format_value(after_val, fname),
                                    }
                                )

                        group_obj = instance.group
                        reference_value = (
                            (
                                getattr(group_obj, "reference", None)
                                or f"#{group_obj.pk}"
                            )
                            if group_obj
                            else f"#{instance.pk}"
                        )
                        status_display_value = (
                            group_obj.get_status_display() if group_obj else ""
                        )

                        email_ctx = {
                            "reservation": instance,
                            "group": group_obj,
                            "reference": reference_value,
                            "status": status_display_value,
                            "changes": changes_payload,
                            "total_price": instance.total_price,
                        }

                        subject_value = f"Reservation updated: {reference_value}"
                        text_body_value = render_to_string(
                            "emails/reservation_edited/reservation_edited.txt",
                            email_ctx,
                        )
                        html_body_value = render_to_string(
                            "emails/reservation_edited/reservation_edited.html",
                            email_ctx,
                        )

                        from_email_value = (
                            getattr(settings, "DEFAULT_FROM_EMAIL", None)
                            or "no-reply@example.com"
                        )
                        send_mail(
                            subject=subject_value,
                            message=text_body_value,
                            from_email=from_email_value,
                            recipient_list=[instance.user.email],
                            html_message=html_body_value,
                            fail_silently=True,
                        )

                success_message = "Reservation updated."
                if important_changed:
                    success_message = (
                        success_message + " Status set to PENDING for re-approval."
                    )
                messages.success(request, success_message)
                return redirect("inventory:reservations")

            except Exception as exc:
                form.add_error(None, str(exc))
        vehicles_qs = Vehicle.objects.all().order_by("name")
        locations_qs = Location.objects.all().order_by("name")
        return render(
            request,
            "inventory/edit_reservation.html",
            {
                "form": form,
                "reservation": reservation_obj,
                "vehicles": vehicles_qs,
                "locations": locations_qs,
            },
        )

    form = ReservationEditForm(instance=reservation_obj)
    vehicles_qs = Vehicle.objects.all().order_by("name")
    locations_qs = Location.objects.all().order_by("name")
    return render(
        request,
        "inventory/edit_reservation.html",
        {
            "form": form,
            "reservation": reservation_obj,
            "vehicles": vehicles_qs,
            "locations": locations_qs,
        },
    )


@login_required
def add_vehicle(request: HttpRequest, group_id: int) -> HttpResponse:
    """
    Add a new vehicle item to an existing reservation group.

    Rules:
        - Disallow changes when the group is RESERVED.
        - Saving a new item sets the group to PENDING.

    Args:
        group_id: ReservationGroup primary key to add into.

    Returns:
        HttpResponse: Render or redirect with user messaging.
    """
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


@user_passes_test(
    lambda u: bool(getattr(u, "is_staff", False))
)  # -------------TODO REMOVE LAMBDA
@require_http_methods(["POST"])
def reject_reservation(request: HttpRequest, group_id: int) -> HttpResponse:
    """
    Staff-only: move a reservation group to REJECTED.

    Args:
        group_id: ReservationGroup primary key.

    Returns:
        HttpResponse: Redirects back to reservations with a status toast.
    """
    try:
        group = transition_group(group_id=group_id, action="reject", actor=request.user)
    except TransitionError as exc:
        messages.info(request, str(exc))
    except Exception as exc:
        messages.error(request, str(exc))
    else:
        reference_value = getattr(group, "reference", None) or str(
            getattr(group, "pk", "")
        )
        messages.success(request, f"Reservation {reference_value} rejected.")
    return redirect("inventory:reservations")
