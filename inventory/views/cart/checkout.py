import secrets


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from inventory.models.cart import Cart, CartItem
from inventory.models.reservation import Reservation, ReservationStatus, ReservationGroup
from inventory.models.vehicle import Vehicle

@login_required
@require_http_methods(["POST"])
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user, is_checked_out=False)

    items = list(
        CartItem.objects.filter(cart=cart)
        .select_related("vehicle", "pickup_location", "return_location")
        .order_by("start_date", "vehicle_id")
    )
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("inventory:view_cart")

    with transaction.atomic():
        vehicle_ids = sorted({it.vehicle_id for it in items})
        list(
            Vehicle.objects.select_for_update()
            .filter(id__in=vehicle_ids)
            .order_by("id")
        )

        for it in items:
            if not Reservation.is_vehicle_available(
                vehicle=it.vehicle,
                start_date=it.start_date,
                end_date=it.end_date,
                pickup=it.pickup_location,
                ret=it.return_location,
            ):
                messages.error(
                    request,
                    f"{it.vehicle} is no longer available for {it.start_date} → {it.end_date}.",
                )
                return redirect("inventory:view_cart")

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
                status=ReservationStatus.PENDING,
                group=group,
            )

        cart.is_checked_out = True
        cart.save(update_fields=["is_checked_out"])
        CartItem.objects.filter(cart=cart).delete()

    messages.success(request, f"Reservation confirmed. Reference: {group.reference}.")
    return redirect("inventory:reservations")