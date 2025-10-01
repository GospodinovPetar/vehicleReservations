from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from config import settings
from inventory.helpers.redirect_back_to_search import redirect_back_to_search
from inventory.models.reservation import (
    Location,
    ReservationGroup,
    ReservationStatus,
    VehicleReservation,
)
from inventory.models.vehicle import Vehicle
from inventory.views.status_switch import TransitionError, transition_group
from mockpay.models import PaymentIntent, PaymentIntentStatus


ACTIVE_STATUSES: Tuple[str, ...] = (
    "PENDING",
    "AWAITING_PAYMENT",
    "RESERVED",
    "ONGOING",
)
ARCHIVED_STATUSES: Tuple[str, ...] = ("COMPLETED", "REJECTED", "CANCELED")

NON_EDITABLE_GROUP_STATUSES: Tuple[str, ...] = (
    ReservationStatus.REJECTED,
    getattr(ReservationStatus, "CANCELED", "CANCELED"),
    ReservationStatus.RESERVED,
)

ONGOING_PER_PAGE: int = 10
ARCHIVED_PER_PAGE: int = 10

MSG_ONLY_VEHICLE_BLOCK = (
    "Can't delete the only vehicle in the reservation; better just reject/cancel "
    "the reservation itself."
)

DEFAULT_FROM_EMAIL: str = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")


def _is_staff_user(user: Any) -> bool:
    """Return True if the user has the `is_staff` boolean attribute set."""
    return bool(getattr(user, "is_staff", False))

def _parse_iso_datetime(value: Optional[str]) -> Optional[timezone.datetime]:
    """Parse an ISO 8601 datetime safely; return None if missing or invalid."""
    if not value:
        return None
    # Try flexible parse first (accepts both date and datetime)
    dt = parse_datetime(value)
    if dt is None:
        # Fallback to fromisoformat for strings like '2025-10-01'
        try:
            dt = timezone.datetime.fromisoformat(value)  # type: ignore[arg-type]
        except Exception:
            return None
    # Normalize to aware in current timezone if naive
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _get_locations_for_vehicle(
    vehicle: Vehicle,
    pickup_id: Optional[str],
    return_id: Optional[str],
) -> Tuple[Optional[Location], Optional[Location]]:
    """
    Resolve pickup/return locations. If ids are missing, fall back to the first
    allowed location for the vehicle.
    """
    if pickup_id:
        pickup = get_object_or_404(Location, pk=pickup_id)
    else:
        pickup = vehicle.available_pickup_locations.first()

    if return_id:
        ret = get_object_or_404(Location, pk=return_id)
    else:
        ret = vehicle.available_return_locations.first()

    return pickup, ret


def _location_allowed(vehicle: Vehicle, loc: Location, *, pickup: bool) -> bool:
    """Return True if a location is allowed as pickup/return for the given vehicle."""
    qs = (
        vehicle.available_pickup_locations
        if pickup
        else vehicle.available_return_locations
    )
    return qs.filter(pk=getattr(loc, "pk", None)).exists()


def _cancel_inflight_intents(group: ReservationGroup) -> None:
    """Cancel in-flight payment intents for a group (requires_confirmation/processing)."""
    intents = (
        PaymentIntent.objects.select_for_update()
        .filter(
            reservation_group=group,
            status__in=[
                PaymentIntentStatus.REQUIRES_CONFIRMATION,
                PaymentIntentStatus.PROCESSING,
            ],
        )
    )
    # Use bulk update semantics while preserving save() side-effects where needed.
    for intent in intents:
        intent.status = PaymentIntentStatus.CANCELED
        intent.save(update_fields=["status"])


def _ensure_group_pending(group: ReservationGroup) -> None:
    """Set group status to PENDING if not already."""
    pending = getattr(ReservationStatus, "PENDING", "PENDING")
    if group.status != pending:
        group.status = pending
        group.save(update_fields=["status"])


def _get_or_create_active_group_for_user(user) -> ReservationGroup:
    """
    Lock and return the latest user's group in AWAITING_PAYMENT or PENDING order.
    If none exists, create a new PENDING group.
    """
    awaiting = (
        ReservationGroup.objects.select_for_update()
        .filter(user=user, status=ReservationStatus.AWAITING_PAYMENT)
        .order_by("-created_at")
        .first()
    )
    if awaiting:
        return awaiting

    pending = (
        ReservationGroup.objects.select_for_update()
        .filter(user=user, status=ReservationStatus.PENDING)
        .order_by("-created_at")
        .first()
    )
    if pending:
        return pending

    return ReservationGroup.objects.create(user=user, status=ReservationStatus.PENDING)


def _render_edit(
    request: HttpRequest,
    form: forms.ModelForm,
    reservation: VehicleReservation,
) -> HttpResponse:
    """Render the edit reservation template with common context."""
    vehicles_qs = Vehicle.objects.all().order_by("name")
    locations_qs = Location.objects.all().order_by("name")
    return render(
        request,
        "inventory/edit_reservation.html",
        {"form": form, "reservation": reservation, "vehicles": vehicles_qs, "locations": locations_qs},
    )

@login_required
@require_http_methods(["POST"])
def reserve(request: HttpRequest) -> HttpResponse:
    """
    Add a selected vehicle and period to the user's active reservation group.

    Flow:
      1) Validate dates and resolve pickup/return locations.
      2) Ensure locations are allowed for the vehicle.
      3) Reuse last AWAITING_PAYMENT/PENDING group, or create a new PENDING group.
      4) If group is AWAITING_PAYMENT, cancel in-flight intents and revert to PENDING.
      5) Create VehicleReservation and ensure group is PENDING.
    """
    form_data = request.POST

    vehicle_id = form_data.get("vehicle")
    start_raw = form_data.get("start")
    end_raw = form_data.get("end")
    pickup_id = form_data.get("pickup_location")
    return_id = form_data.get("return_location")

    vehicle = get_object_or_404(Vehicle, pk=vehicle_id)

    start_dt = _parse_iso_datetime(start_raw)
    end_dt = _parse_iso_datetime(end_raw)

    if start_dt is None or end_dt is None or end_dt <= start_dt:
        messages.error(request, "Start date must be before end date.")
        return redirect_back_to_search(start_raw, end_raw)

    pickup_loc, return_loc = _get_locations_for_vehicle(vehicle, pickup_id, return_id)
    if pickup_loc is None or return_loc is None:
        messages.error(request, "This vehicle has no configured pickup/return locations.")
        return redirect_back_to_search(start_raw, end_raw)

    if not _location_allowed(vehicle, pickup_loc, pickup=True):
        messages.error(request, "Selected pickup location is not available for this vehicle.")
        return redirect_back_to_search(start_raw, end_raw)

    if not _location_allowed(vehicle, return_loc, pickup=False):
        messages.error(request, "Selected return location is not available for this vehicle.")
        return redirect_back_to_search(start_raw, end_raw)

    try:
        with transaction.atomic():
            group = _get_or_create_active_group_for_user(request.user)

            if group.status == ReservationStatus.RESERVED:
                messages.error(request, "You can’t modify a reserved reservation.")
                return redirect("inventory:reservations")

            if group.status == ReservationStatus.AWAITING_PAYMENT:
                _cancel_inflight_intents(group)
                _ensure_group_pending(group)
                group.refresh_from_db(fields=["status"])

            reservation = VehicleReservation(
                user=request.user,
                vehicle=vehicle,
                pickup_location=pickup_loc,
                return_location=return_loc,
                start_date=start_dt,
                end_date=end_dt,
                group=group,
            )
            reservation.full_clean()
            reservation.save()

            _ensure_group_pending(group)
            group.refresh_from_db(fields=["status"])

    except Exception as exc:  # noqa: BLE001
        messages.error(request, str(exc))
        return redirect_back_to_search(start_raw, end_raw)

    messages.success(request, "Vehicle added to your reservation.")
    return redirect("inventory:reservations")


class ReservationEditForm(forms.ModelForm):
    """Form for editing a reservation's key fields (vehicle, locations, dates)."""

    class Meta:
        model = VehicleReservation
        fields = ["vehicle", "pickup_location", "return_location", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


@login_required
def my_reservations(request: HttpRequest) -> HttpResponse:
    """
    Logged-in user's reservation list (active + archived), with filtering + pagination.
    Renders: inventory/reservations.html
    """
    pickup_q = (request.GET.get("pickup") or "").strip()
    dropoff_q = (request.GET.get("dropoff") or "").strip()
    status_q = (request.GET.get("status") or "").strip()

    res_qs = (
        VehicleReservation.objects.filter(user=request.user)
        .select_related("vehicle", "pickup_location", "return_location", "group")
    )

    if pickup_q:
        res_qs = res_qs.filter(
            Q(pickup_location__name__iexact=pickup_q)
            | Q(pickup_location_snapshot__iexact=pickup_q)
        )
    if dropoff_q:
        res_qs = res_qs.filter(
            Q(return_location__name__iexact=dropoff_q)
            | Q(return_location_snapshot__iexact=dropoff_q)
        )

    # Collect group ids to build active/archived buckets
    group_ids: List[int] = list(res_qs.values_list("group_id", flat=True).distinct())

    active_groups_qs = ReservationGroup.objects.filter(id__in=group_ids, status__in=ACTIVE_STATUSES)
    archived_groups_qs = ReservationGroup.objects.filter(id__in=group_ids, status__in=ARCHIVED_STATUSES)

    if status_q:
        active_groups_qs = active_groups_qs.filter(status=status_q)
        archived_groups_qs = archived_groups_qs.filter(status=status_q)

    active_groups = list(active_groups_qs.order_by("-created_at"))
    archived_groups = list(archived_groups_qs.order_by("-created_at"))

    # Group reservations by group id
    res_by_group: Dict[int, List[VehicleReservation]] = defaultdict(list)
    for r in res_qs:
        res_by_group[r.group_id].append(r)

    # Keep only groups that actually have reservations after filters
    active_groups = [g for g in active_groups if res_by_group.get(g.id)]
    archived_groups = [g for g in archived_groups if res_by_group.get(g.id)]

    # Attach filtered reservations for convenience in the template
    for g in active_groups:
        g.filtered_reservations = res_by_group[g.id]  # type: ignore[attr-defined]
    for g in archived_groups:
        g.filtered_reservations = res_by_group[g.id]  # type: ignore[attr-defined]

    # Pagination
    ongoing_page_num = request.GET.get("ongoing_page", 1)
    archived_page_num = request.GET.get("archived_page", 1)

    ongoing_page_obj = Paginator(active_groups, ONGOING_PER_PAGE).get_page(ongoing_page_num)
    archived_page_obj = Paginator(archived_groups, ARCHIVED_PER_PAGE).get_page(archived_page_num)

    # Preserve filters across paginated links
    qs_all = request.GET.copy()

    ongoing_params_qs = qs_all.copy()
    ongoing_params_qs.pop("ongoing_page", None)
    ongoing_params = ongoing_params_qs.urlencode()

    archived_params_qs = qs_all.copy()
    archived_params_qs.pop("archived_page", None)
    archived_params = archived_params_qs.urlencode()

    locations = list(Location.objects.order_by("name").values_list("name", flat=True).distinct())

    return render(
        request,
        "inventory/reservations.html",
        {
            "ongoing_page_obj": ongoing_page_obj,
            "archived_page_obj": archived_page_obj,
            "ongoing_params": ongoing_params,
            "archived_params": archived_params,
            "locations": locations,
        },
    )


@user_passes_test(_is_staff_user)
@require_http_methods(["POST"])
def approve_group(request: HttpRequest, group_id: int) -> HttpResponse:
    """Staff-only: move a reservation group from PENDING to AWAITING_PAYMENT."""
    try:
        group = transition_group(group_id=group_id, action="approve", actor=request.user)
    except TransitionError as exc:
        messages.info(request, str(exc))
    except Exception as exc:  # noqa: BLE001
        messages.error(request, str(exc))
    else:
        ref = getattr(group, "reference", None) or str(getattr(group, "pk", ""))
        messages.success(request, f"Reservation {ref} approved. Awaiting payment.")
    return redirect("inventory:reservations")


@login_required
@require_http_methods(["POST"])
def cancel_reservation(request: HttpRequest, group_id: int) -> HttpResponse:
    """Cancel a user's reservation group (if allowed by current status)."""
    try:
        group = transition_group(group_id=group_id, action="cancel", actor=request.user)
    except TransitionError as exc:
        messages.info(request, str(exc))
    except Exception as exc:  # noqa: BLE001
        messages.error(request, str(exc))
    else:
        ref = getattr(group, "reference", None) or str(getattr(group, "pk", ""))
        messages.info(request, f"Reservation {ref} canceled.")
    return redirect("inventory:reservations")


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_reservation(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Remove a vehicle from a reservation group.

    Admin rules:
      - If it's the ONLY vehicle: block, show message, no changes.
      - If there are multiple vehicles: delete and set status to PENDING.

    Non-admin rules (unchanged):
      - Can't delete the only vehicle.
      - On delete, cancel in-flight payment intents. No status change.

    Global rules:
      - Disallow edits for groups in REJECTED, CANCELED, or RESERVED.
    """
    is_admin = bool(request.user.is_staff or request.user.is_superuser)

    base_qs = VehicleReservation.objects.select_related("group")
    if not is_admin:
        base_qs = base_qs.filter(user=request.user)

    reservation = get_object_or_404(base_qs, pk=pk)
    group = reservation.group

    if group is None:
        messages.error(request, MSG_ONLY_VEHICLE_BLOCK)
        return redirect("inventory:reservations")

    group = ReservationGroup.objects.select_for_update().get(pk=group.pk)

    if group.status in NON_EDITABLE_GROUP_STATUSES:
        messages.error(request, "This reservation cannot be modified.")
        return redirect("inventory:reservations")

    total_in_group = VehicleReservation.objects.filter(group=group).count()

    if is_admin:
        if total_in_group <= 1:
            messages.error(request, MSG_ONLY_VEHICLE_BLOCK)
            return redirect("accounts:reservation-list")

        reservation.delete()
        _ensure_group_pending(group)
        _cancel_inflight_intents(group)

        messages.success(
            request, "Vehicle removed. Reservation status set to PENDING for re-approval."
        )
        return redirect("accounts:reservation-list")

    if total_in_group <= 1:
        messages.error(
            request,
            "You cannot remove the only vehicle in this reservation. Try cancelling the reservation.",
        )
        return redirect("accounts:reservation-list")

    reservation.delete()
    _cancel_inflight_intents(group)
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
    """
    qs = VehicleReservation.objects.select_related("vehicle", "group", "user")
    user_role = getattr(request.user, "role", "")
    if user_role in ("manager", "admin"):
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

            has_date_error = False
            if new_start is None or new_end is None:
                form.add_error(None, "Please provide both pickup and return dates.")
                has_date_error = True
            else:
                if new_start >= new_end:
                    form.add_error("end_date", "End date must be after start date.")
                    has_date_error = True
                today = timezone.localdate()
                if new_start < today:
                    form.add_error("start_date", "Pickup date cannot be in the past.")
                    has_date_error = True
                if new_end < today:
                    form.add_error("end_date", "Return date cannot be in the past.")
                    has_date_error = True

            has_location_error = False
            if selected_vehicle and selected_pickup:
                if selected_vehicle.available_pickup_locations.exists():
                    if not selected_vehicle.available_pickup_locations.filter(pk=selected_pickup.pk).exists():
                        form.add_error("pickup_location", "Pickup location not allowed for this vehicle.")
                        has_location_error = True

            if selected_vehicle and selected_return:
                if selected_vehicle.available_return_locations.exists():
                    if not selected_vehicle.available_return_locations.filter(pk=selected_return.pk).exists():
                        form.add_error("return_location", "Return location not allowed for this vehicle.")
                        has_location_error = True

            if form.errors or has_date_error or has_location_error:
                return _render_edit(request, form, reservation)

            overlaps_qs = VehicleReservation.objects.filter(
                vehicle_id=(selected_vehicle.pk if selected_vehicle else None),
                group__status__in=ReservationStatus.blocking(),
                start_date__lt=new_end,
                end_date__gt=new_start,
            ).exclude(pk=reservation.pk)
            if overlaps_qs.exists():
                form.add_error("start_date", "This vehicle is not available in the selected period.")
                return _render_edit(request, form, reservation)

            try:
                with transaction.atomic():
                    before_snapshot: Dict[str, Any] = {
                        "vehicle": reservation.vehicle,
                        "pickup_location": reservation.pickup_location,
                        "return_location": reservation.return_location,
                        "start_date": reservation.start_date,
                        "end_date": reservation.end_date,
                    }

                    instance: VehicleReservation = form.save(commit=False)
                    instance.full_clean()
                    instance.save()

                    important_fields = {"vehicle", "pickup_location", "return_location", "start_date", "end_date"}
                    changed_fields = set(form.changed_data).intersection(important_fields)
                    important_changed = bool(changed_fields)

                    if important_changed and instance.group_id:
                        _ensure_group_pending(instance.group)

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

                        def _fmt(value: Any, field: str) -> str:
                            if field in {"start_date", "end_date"} and value:
                                try:
                                    return value.strftime("%Y-%m-%d")
                                except Exception:
                                    return str(value)
                            return str(value) if value is not None else "-"

                        changes_payload: List[Dict[str, str]] = []
                        for fname in ["vehicle", "pickup_location", "return_location", "start_date", "end_date"]:
                            if fname in changed_fields:
                                changes_payload.append(
                                    {
                                        "label": label_map[fname],
                                        "before": _fmt(before_snapshot.get(fname), fname),
                                        "after": _fmt(after_snapshot.get(fname), fname),
                                    }
                                )

                        group_obj = instance.group
                        reference_value = (
                            (getattr(group_obj, "reference", None) or f"#{group_obj.pk}")
                            if group_obj
                            else f"#{instance.pk}"
                        )
                        status_display = group_obj.get_status_display() if group_obj else ""

                        email_ctx = {
                            "reservation": instance,
                            "group": group_obj,
                            "reference": reference_value,
                            "status": status_display,
                            "changes": changes_payload,
                            "total_price": instance.total_price,
                        }

                        subject = f"Reservation updated: {reference_value}"
                        text_body = render_to_string("emails/reservation_edited/reservation_edited.txt", email_ctx)
                        html_body = render_to_string("emails/reservation_edited/reservation_edited.html", email_ctx)

                        send_mail(
                            subject=subject,
                            message=text_body,
                            from_email=DEFAULT_FROM_EMAIL,
                            recipient_list=[instance.user.email],
                            html_message=html_body,
                            fail_silently=True,
                        )

                success_message = "Reservation updated."
                if important_changed:
                    success_message += " Status set to PENDING for re-approval."
                messages.success(request, success_message)
                return redirect("inventory:reservations")

            except Exception as exc:
                form.add_error(None, str(exc))
                return _render_edit(request, form, reservation)

        return _render_edit(request, form, reservation)

    form = ReservationEditForm(instance=reservation)
    return _render_edit(request, form, reservation)


@user_passes_test(_is_staff_user)
@require_http_methods(["POST"])
def reject_reservation(request: HttpRequest, group_id: int) -> HttpResponse:
    """Staff-only: move a reservation group to REJECTED."""
    try:
        group = transition_group(group_id=group_id, action="reject", actor=request.user)
    except TransitionError as exc:
        messages.info(request, str(exc))
    except Exception as exc:  # noqa: BLE001
        messages.error(request, str(exc))
    else:
        ref = getattr(group, "reference", None) or str(getattr(group, "pk", ""))
        messages.success(request, f"Reservation {ref} rejected.")
    return redirect("inventory:reservations")
