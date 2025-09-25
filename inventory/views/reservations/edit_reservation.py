from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from inventory.models.reservation import (
    Location,
    VehicleReservation,
    ReservationStatus,
    BLOCKING_STATUSES,
)
from inventory.models.vehicle import Vehicle
from django.utils import timezone

from inventory.views.reservations.reservation_edit_form import ReservationEditForm

from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings


@login_required
def edit_reservation(request, pk):
    qs = VehicleReservation.objects.select_related("vehicle", "group", "user")
    if getattr(request.user, "role", "") in ("manager", "admin"):
        reservation = get_object_or_404(qs, pk=pk)
    else:
        reservation = get_object_or_404(qs.filter(user=request.user), pk=pk)

    if request.method == "POST":
        form = ReservationEditForm(request.POST, instance=reservation)

        if form.is_valid():
            selected_vehicle = form.cleaned_data.get("vehicle")
            selected_pickup = form.cleaned_data.get("pickup_location")
            selected_return = form.cleaned_data.get("return_location")
            new_start = form.cleaned_data.get("start_date")
            new_end = form.cleaned_data.get("end_date")

            original_start = reservation.start_date
            original_end = reservation.end_date

            if not new_start or not new_end:
                form.add_error(None, "Please provide both pickup and return dates.")
            else:
                if new_start >= new_end:
                    form.add_error("end_date", "End date must be after start date.")

                today = timezone.localdate()
                if new_start < today:
                    form.add_error("start_date", "Pickup date cannot be in the past.")
                if new_end < today:
                    form.add_error("end_date", "Return date cannot be in the past.")

            if (
                selected_vehicle
                and selected_pickup
                and selected_vehicle.available_pickup_locations.exists()
            ):
                if not selected_vehicle.available_pickup_locations.filter(
                    pk=selected_pickup.pk
                ).exists():
                    form.add_error(
                        "pickup_location",
                        "Pickup location not allowed for this vehicle.",
                    )

            if (
                selected_vehicle
                and selected_return
                and selected_vehicle.available_return_locations.exists()
            ):
                if not selected_vehicle.available_return_locations.filter(
                    pk=selected_return.pk
                ).exists():
                    form.add_error(
                        "return_location",
                        "Return location not allowed for this vehicle.",
                    )

            if form.errors:
                return render(
                    request,
                    "inventory/edit_reservation.html",
                    {
                        "form": form,
                        "reservation": reservation,
                        "vehicles": Vehicle.objects.all().order_by("name"),
                        "locations": Location.objects.all().order_by("name"),
                    },
                )

            overlaps = VehicleReservation.objects.filter(
                vehicle_id=selected_vehicle.pk,
                group__status__in=BLOCKING_STATUSES,
                start_date__lt=new_end,
                end_date__gt=new_start,
            ).exclude(pk=reservation.pk)

            if overlaps.exists():
                form.add_error(
                    "start_date",
                    "This vehicle is not available in the selected period.",
                )
                return render(
                    request,
                    "inventory/edit_reservation.html",
                    {
                        "form": form,
                        "reservation": reservation,
                        "vehicles": Vehicle.objects.all().order_by("name"),
                        "locations": Location.objects.all().order_by("name"),
                    },
                )

            try:
                with transaction.atomic():
                    before = {
                        "vehicle": reservation.vehicle,
                        "pickup_location": reservation.pickup_location,
                        "return_location": reservation.return_location,
                        "start_date": reservation.start_date,
                        "end_date": reservation.end_date,
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
                    changed_fields = set(form.changed_data) & important_fields
                    important_changed = bool(changed_fields)

                    if dates_changed:
                        instance.status = ReservationStatus.PENDING
                        instance.save(
                            update_fields=["status"]
                        )  # triggers your status-change signal
                    if important_changed and instance.group_id:
                        instance.group.status = ReservationStatus.PENDING
                        instance.group.save(update_fields=["status"])

                    if important_changed and instance.user and instance.user.email:
                        after = {
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

                        def fmt(val, field):
                            if field in ("start_date", "end_date") and val:
                                return val.strftime("%Y-%m-%d")
                            return str(val) if val is not None else "-"

                        changes = [
                            {
                                "label": label_map[f],
                                "before": fmt(before[f], f),
                                "after": fmt(after[f], f),
                            }
                            for f in ["vehicle", "pickup_location", "return_location", "start_date", "end_date"]
                            if f in changed_fields
                        ]

                        group = instance.group
                        ctx = {
                            "reservation": instance,
                            "group": group,
                            "reference": (getattr(group, "reference", None) or f"#{group.pk}") if group else f"#{instance.pk}",
                            "status": group.get_status_display() if group else "",
                            "changes": changes,
                            "total_price": instance.total_price,
                        }

                        subject = f"Reservation updated: {ctx['reference']}"
                        text_body = render_to_string("emails/reservation_edited/reservation_edited.txt", ctx)
                        html_body = render_to_string("emails/reservation_edited/reservation_edited.html", ctx)

                        send_mail(
                            subject=subject,
                            message=text_body,
                            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@example.com",
                            recipient_list=[instance.user.email],
                            html_message=html_body,
                            fail_silently=True,
                        )
                    if dates_changed and instance.group_id:
                        instance.group.status = ReservationStatus.PENDING
                        instance.group.save(update_fields=["status"])

                messages.success(
                    request,
                    "Reservation updated."
                    + (" Status set to PENDING for re-approval." if important_changed else ""),
                )
                return redirect("inventory:reservations")

            except Exception as exc:
                form.add_error(None, str(exc))

    else:
        form = ReservationEditForm(instance=reservation)

    vehicles = Vehicle.objects.all().order_by("name")
    locations = Location.objects.all().order_by("name")
    return render(
        request,
        "inventory/edit_reservation.html",
        {
            "form": form,
            "reservation": reservation,
            "vehicles": vehicles,
            "locations": locations,
        },
    )
