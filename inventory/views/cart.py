from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
import secrets

from inventory.models.cart import Cart, CartItem, ReservationGroup
from inventory.models.reservation import Location, Reservation, ReservationStatus
from inventory.models.vehicle import Vehicle
from inventory.helpers.parse_iso_date import parse_iso_date
from inventory.helpers.pricing import RateTable, quote_total


@login_required
@require_http_methods(["POST"])
def add_to_cart(request):
    vehicle = get_object_or_404(Vehicle, pk=request.POST.get("vehicle"))
    start_date = parse_iso_date(request.POST.get("start"))
    end_date = parse_iso_date(request.POST.get("end"))
    pickup = Location.objects.filter(pk=request.POST.get("pickup_location")).first()
    return_loc = Location.objects.filter(pk=request.POST.get("return_location")).first()

    if not start_date or not end_date:
        messages.error(request, "Start and end dates are required.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    cart = Cart.get_or_create_active(request.user)
    item = CartItem(
        cart=cart,
        vehicle=vehicle,
        start_date=start_date,
        end_date=end_date,
        pickup_location=pickup,
        return_location=return_loc,
    )
    try:
        item.full_clean()
        item.save()
    except Exception as e:
        messages.error(request, f"Could not add to cart: {e}")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    messages.success(request, f"Added {vehicle} to cart.")
    return redirect("inventory:view_cart")


@login_required
def view_cart(request):
    cart = Cart.get_or_create_active(request.user)
    items = list(
        cart.items.select_related("vehicle", "pickup_location", "return_location")
    )
    rows = []
    for it in items:
        q = quote_total(
            it.start_date,
            it.end_date,
            RateTable(day=float(it.vehicle.price_per_day), currency="EUR"),
        )
        rows.append({"item": it, "days": q["days"], "total": Decimal(str(q["total"]))})
    return render(request, "inventory/cart.html", {"cart": cart, "rows": rows})


@login_required
@require_http_methods(["POST"])
def remove_from_cart(request, item_id):
    cart = Cart.get_or_create_active(request.user)
    item = get_object_or_404(cart.items, pk=item_id)
    item.delete()
    messages.success(request, "Removed item from cart.")
    return redirect("inventory:view_cart")


@login_required
@require_http_methods(["POST"])
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user, is_checked_out=False)
    items = list(
        cart.items.select_related(
            "vehicle", "pickup_location", "return_location"
        ).order_by("start_date", "vehicle_id")
    )
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("inventory:view_cart")

    for it in items:
        available_ids = set(
            Reservation.available_vehicles(
                start_date=it.start_date,
                end_date=it.end_date,
                pickup_location=it.pickup_location,
                return_location=it.return_location,
            )
        )
        if it.vehicle_id not in available_ids:
            messages.error(
                request,
                f"{it.vehicle} is no longer available for {it.start_date} \N{RIGHTWARDS ARROW} {it.end_date}.",
            )
            return redirect("inventory:view_cart")

    with transaction.atomic():
        group = ReservationGroup.objects.create(user=request.user)
        if not getattr(group, "reference", None):

            group.reference = secrets.token_hex(4).upper()
            group.save(update_fields=["reference"])

        for it in items:
            Reservation.objects.create(
                user=request.user,
                vehicle=it.vehicle,
                pickup_location=it.pickup_location,
                return_location=it.return_location,
                start_date=it.start_date,
                end_date=it.end_date,
                status=ReservationStatus.RESERVED,
                group=group,
            )

        cart.is_checked_out = True
        cart.save(update_fields=["is_checked_out"])
        cart.items.all().delete()

    messages.success(request, f"Reservation confirmed. Reference: {group.reference}.")
    return redirect("inventory:reservations")


@login_required
def my_reservations(request):
    active_reservations_qs = (
        Reservation.objects.exclude(status=ReservationStatus.REJECTED)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("-start_date")
    )

    groups = (
        ReservationGroup.objects.filter(user=request.user)
        .prefetch_related(Prefetch("reservations", queryset=active_reservations_qs))
        .order_by("-created_at")
    )

    ungroupped = (
        Reservation.objects.filter(user=request.user, group__isnull=True)
        .exclude(status=ReservationStatus.REJECTED)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("-start_date")
    )

    canceled = (
        Reservation.objects.filter(user=request.user, status=ReservationStatus.CANCELED)
        .select_related("vehicle", "pickup_location", "return_location", "group")
        .order_by("-start_date")
    )

    rejected = (
        Reservation.objects.filter(user=request.user, status=ReservationStatus.REJECTED)
        .select_related("vehicle", "pickup_location", "return_location", "group")
        .order_by("-start_date")
    )

    return render(
        request,
        "inventory/my_reservations.html",
        {"groups": groups, "ungroupped": ungroupped, "canceled": canceled},
    )


@login_required
def cancel_group(request, group_id):
    group = get_object_or_404(ReservationGroup, pk=group_id, user=request.user)
    ref = group.reference or f"#{group.pk}"
    with transaction.atomic():
        cancelable = ~Q(status=ReservationStatus.REJECTED)
        if hasattr(ReservationStatus, "COMPLETED"):
            cancelable &= ~Q(status=ReservationStatus.COMPLETED)
        updated = group.reservations.filter(cancelable).update(
            status=ReservationStatus.CANCELED
        )
        group.delete()
    messages.success(request, f"Canceled {updated} reservation(s) from group {ref}.")
    return redirect("inventory:reservations")
