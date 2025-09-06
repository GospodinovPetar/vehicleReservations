from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict

DAY = 1
WEEK = 7
MONTH = 30

@dataclass
class RateTable:
    day: Optional[float] = None
    week: Optional[float] = None
    month: Optional[float] = None
    currency: str = "EUR"

def _min_cost(days: int, rates: RateTable):
    big = 10**15
    cost = [0.0] + [big] * days
    take = [None] * (days + 1)

    choices = []
    if rates.day is not None: choices.append(("day", DAY, float(rates.day)))
    if rates.week is not None: choices.append(("week", WEEK, float(rates.week)))
    if rates.month is not None: choices.append(("month", MONTH, float(rates.month)))
    if not choices:
        raise ValueError("No prices configured for this vehicle")

    for d in range(1, days + 1):
        for label, span, unit_price in choices:
            prev = max(0, d - span)
            c = cost[prev] + unit_price
            if c < cost[d]:
                cost[d] = c
                take[d] = (label, span, unit_price)

    breakdown: Dict[str, Dict[str, float]] = {}
    d = days
    while d > 0:
        label, span, unit_price = take[d]
        b = breakdown.setdefault(label, {"units": 0, "unit_amount": unit_price})
        b["units"] += 1
        d -= span

    out = []
    order = {"month": 3, "week": 2, "day": 1}
    for label, info in breakdown.items():
        subtotal = info["units"] * info["unit_amount"]
        out.append({
            "period": label,
            "units": int(info["units"]),
            "unit_amount": round(info["unit_amount"], 2),
            "subtotal": round(subtotal, 2),
        })
    out.sort(key=lambda x: order[x["period"]], reverse=True)
    return round(cost[days], 2), out

def quote_total(start: date, end: date, rates: RateTable):
    if end <= start:
        raise ValueError("end_date must be after start_date")
    days = (end - start).days
    total, breakdown = _min_cost(days, rates)
    return {"days": days, "total": total, "breakdown": breakdown, "currency": rates.currency}
