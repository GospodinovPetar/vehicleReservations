from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from inventory.helpers.pricing import RateTable, quote_total
from cart.models.cart import Cart, CartItem


@login_required
def view_cart(request: HttpRequest) -> HttpResponse:
    cart_obj: Cart = Cart.get_or_create_active(request.user)

    items_qs = CartItem.objects.filter(cart=cart_obj).select_related(
        "vehicle",
        "pickup_location",
        "return_location",
    )
    items: List[CartItem] = list(items_qs)

    rows: List[Dict[str, Any]] = []
    for item in items:
        vehicle_obj = getattr(item, "vehicle", None)
        day_rate_float = 0.0
        if vehicle_obj is not None:
            price_attr = getattr(vehicle_obj, "price_per_day", 0)
            day_rate_float = float(price_attr or 0)

        rate_table = RateTable(day=day_rate_float, currency="EUR")
        quote = quote_total(item.start_date, item.end_date, rate_table)

        days_value = int(quote.get("days", 0))
        total_value = Decimal(str(quote.get("total", "0")))

        rows.append(
            {
                "item": item,
                "days": days_value,
                "total": total_value,
            }
        )

    cart_total: Decimal = sum((row["total"] for row in rows), Decimal("0"))

    context: Dict[str, Any] = {
        "cart": cart_obj,
        "rows": rows,
        "cart_total": cart_total,
    }
    return render(request, "cart/cart.html", context)
