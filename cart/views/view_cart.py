from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from inventory.helpers.pricing import RateTable, quote_total
from cart.models.cart import Cart, CartItem

@login_required
def view_cart(request):
    cart = Cart.get_or_create_active(request.user)
    items = list(
        CartItem.objects.filter(cart=cart).select_related(
            "vehicle", "pickup_location", "return_location"
        )
    )

    rows = []
    for it in items:
        q = quote_total(
            it.start_date,
            it.end_date,
            RateTable(day=float(it.vehicle.price_per_day), currency="EUR"),
        )
        rows.append({"item": it, "days": q["days"], "total": Decimal(str(q["total"]))})

    return render(request, "cart/cart.html", {"cart": cart, "rows": rows})