from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List

@dataclass
class RateTable:
    day: Optional[float] = None
    week: Optional[float] = None  # unused
    month: Optional[float] = None  # unused
    currency: str = "EUR"

def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0

def _breakdown_to_lines(daily_price: float, months: int, weeks: int, days: int) -> List[Dict[str, object]]:
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
        lines.append({
            "period": "week",
            "units": weeks,
            "unit_amount": round(6 * daily_price, 2),
            "note": "7-day block charged as 6 days",
            "subtotal": round(weeks * 6 * daily_price, 2),
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
    Compute cost by grouping into 30-day 'months' and 7-day 'weeks'.
    If month_first=True, take as many 30-day blocks as possible, then weeks, then days.
    If month_first=False, take weeks first, then months from the remainder, then days.
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

    total = (m * 26 + w * 6 + d) * daily_price
    breakdown = _breakdown_to_lines(daily_price, m, w, d)
    return {
        "days": days_total,
        "total": round(total, 2),
        "breakdown": breakdown,
    }

def quote_total(
    start_date: date, end_date: date, rate_table: RateTable
) -> Dict[str, object]:
    """
    Compute the total using:
      - 7-day blocks charged as 6 days
      - 30-day blocks charged as 26 days
    End date is treated as exclusive: total_days = (end_date - start_date).days
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
