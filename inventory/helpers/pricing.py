from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List

@dataclass
class RateTable:
    day: Optional[float] = None
    week: Optional[float] = None   # unused
    month: Optional[float] = None  # unused
    currency: str = "EUR"

def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0

def _breakdown_to_lines(daily_price: float, months: int, weeks: int, days: int) -> List[Dict[str, object]]:
    """
    Build a human-readable cost breakdown with the new tiered week discount:
      - Weeks: charge (weeks*7 - min(weeks, 3)) days
      - Months: charge (months*26) days (30-day blocks charged as 26)
    """
    lines: List[Dict[str, object]] = []

    if months:
        lines.append({
            "period": "month",
            "units": months,
            "unit_amount": round(26 * daily_price, 2),
            "note": "30-day block charged as 26 days",
            "subtotal": round(months * 26 * daily_price, 2),
        })

    if weeks:
        charged_week_days = weeks * 7 - min(weeks, 3)  # cap freebies at 3 days across the weeks block
        lines.append({
            "period": "weeks",
            "units": weeks,
            "unit_amount": round(daily_price, 2),  # informational (per-day); subtotal reflects discount
            "note": f"{weeks}×7 days charged as {charged_week_days} days (tiered week discount)",
            "subtotal": round(charged_week_days * daily_price, 2),
        })

    if days:
        lines.append({
            "period": "day",
            "units": days,
            "unit_amount": round(daily_price, 2),
            "subtotal": round(days * daily_price, 2),
        })

    return lines

def _cost_for(days_total: int, daily_price: float, month_first: bool) -> Dict[str, object]:
    """
    Compute cost by grouping into 30-day 'months' (charged as 26 days) and 7-day 'weeks'
    with a tiered free-day rule:
      - 1 week => 1 day free
      - 2 weeks => 2 days free
      - 3 weeks => 3 days free
      - 4+ weeks => still only 3 days total free via the 'weeks' bucket (months handle longer spans)
    The remainder is charged per-day.
    """
    remaining = days_total
    m = w = d = 0

    if month_first:
        m = remaining // 30
        remaining -= m * 30
        w = remaining // 7
        remaining -= w * 7
        d = remaining
    else:
        w = remaining // 7
        remaining -= w * 7
        m = remaining // 30
        remaining -= m * 30
        d = remaining

    # Apply pricing rules
    charged_month_days = m * 26
    charged_week_days = w * 7 - min(w, 3)  # tiered: up to 3 days free across the weeks chunk
    charged_days = charged_month_days + charged_week_days + d

    total = charged_days * daily_price
    breakdown = _breakdown_to_lines(daily_price, m, w, d)

    return {
        "days": days_total,
        "total": round(total, 2),
        "breakdown": breakdown,
    }

def quote_total(start_date: date, end_date: date, rate_table: RateTable) -> Dict[str, object]:
    """
    Total uses:
      - Weeks: 1→6 paid, 2→12 paid, 3→18 paid (free days equal to week count, capped at 3)
      - Months: 30-day blocks charged as 26 days (4 free)
      - End date exclusive: total_days = (end_date - start_date).days
    We try both month-first and week-first packings and take the cheaper.
    """
    if not start_date or not end_date or end_date <= start_date:
        return {
            "days": 0,
            "total": 0.0,
            "breakdown": [],
            "currency": rate_table.currency if rate_table else "EUR",
        }

    daily_price = _safe_float(getattr(rate_table, "day", None))
    if daily_price <= 0:
        return {
            "days": 0,
            "total": 0.0,
            "breakdown": [],
            "currency": rate_table.currency if rate_table else "EUR",
        }

    total_days = (end_date - start_date).days

    a = _cost_for(total_days, daily_price, month_first=True)
    b = _cost_for(total_days, daily_price, month_first=False)
    best = a if a["total"] <= b["total"] else b

    return {
        **best,
        "currency": rate_table.currency if rate_table else "EUR",
    }
