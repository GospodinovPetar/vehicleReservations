from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings

from inventory.models.reservation import Location, VehicleReservation, ReservationStatus
from inventory.models.vehicle import Vehicle
from inventory.views.reservations.reservation_edit_form import ReservationEditForm


@login_required
@require_http_methods(["GET", "POST"])
def edit_reservation(request: HttpRequest, pk: int) -> HttpResponse:
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
