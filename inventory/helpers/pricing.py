from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List, Any


@dataclass
class RateTable:
    """Simple rate table for quoting.

    Attributes:
        day: Daily price (used for all calculations; `week`/`month` are informational).
        week: Optional weekly price (not directly used by this algorithm).
        month: Optional monthly price (not directly used by this algorithm).
        currency: Currency code for display (e.g., "EUR").
    """
    day: Optional[float] = None
    week: Optional[float] = None
    month: Optional[float] = None
    currency: str = "EUR"


def _safe_float(value: Any) -> float:
    """Safely coerce a value to float; returns 0.0 on failure."""
    try:
        return float(value)
    except Exception:
        return 0.0


def _breakdown_to_lines(
    daily_price: float,
    months_count: int,
    weeks_count: int,
    days_count: int,
) -> List[Dict[str, Any]]:
    """Build a human-friendly breakdown list for months/weeks/days.

    Notes:
        - Month line charges 26 days per 30-day block.
        - Week line applies tiered discount: 1 free day per week, capped at 3 total.

    Args:
        daily_price: Unit price per day.
        months_count: Number of 30-day blocks.
        weeks_count: Number of 7-day blocks.
        days_count: Remaining single days.

    Returns:
        List of dicts with keys: period, units, unit_amount, subtotal, and optional note.
    """
    lines: List[Dict[str, Any]] = []

    if months_count > 0:
        unit_amount_month = round(26.0 * daily_price, 2)
        subtotal_months = round(months_count * 26.0 * daily_price, 2)
        lines.append(
            {
                "period": "month",
                "units": months_count,
                "unit_amount": unit_amount_month,
                "note": "30-day block charged as 26 days",
                "subtotal": subtotal_months,
            }
        )

    if weeks_count > 0:
        free_days_from_weeks = weeks_count
        if free_days_from_weeks > 3:
            free_days_from_weeks = 3
        charged_week_days = weeks_count * 7 - free_days_from_weeks
        unit_amount_week_info = round(daily_price, 2)
        subtotal_weeks = round(charged_week_days * daily_price, 2)
        lines.append(
            {
                "period": "weeks",
                "units": weeks_count,
                "unit_amount": unit_amount_week_info,
                "note": f"{weeks_count}×7 days charged as {charged_week_days} days (tiered week discount)",
                "subtotal": subtotal_weeks,
            }
        )

    if days_count > 0:
        unit_amount_day = round(daily_price, 2)
        subtotal_days = round(days_count * daily_price, 2)
        lines.append(
            {
                "period": "day",
                "units": days_count,
                "unit_amount": unit_amount_day,
                "subtotal": subtotal_days,
            }
        )

    return lines


def _cost_for(days_total: int, daily_price: float, month_first: bool) -> Dict[str, Any]:
    """Compute total and breakdown for a given total-day span and strategy.

    Strategy:
        - If `month_first` is True, consume as many 30-day blocks, then weeks, then days.
        - Otherwise, consume weeks first, then months, then days.
        - Month: each block billed as 26 days.
        - Week: 1 free day per week, capped at 3 free days total.

    Args:
        days_total: Total number of rental days.
        daily_price: Price per single day.
        month_first: Whether to prioritize 30-day blocks over weeks.

    Returns:
        Dict with keys:
            - "days": original `days_total`
            - "total": computed price (rounded to 2 decimals)
            - "breakdown": list suitable for UI display
    """
    remaining_days = days_total
    months_count = 0
    weeks_count = 0

    if month_first:
        if remaining_days >= 30:
            months_count = remaining_days // 30
            remaining_days = remaining_days - months_count * 30
        if remaining_days >= 7:
            weeks_count = remaining_days // 7
            remaining_days = remaining_days - weeks_count * 7
        days_count = remaining_days
    else:
        if remaining_days >= 7:
            weeks_count = remaining_days // 7
            remaining_days = remaining_days - weeks_count * 7
        if remaining_days >= 30:
            months_count = remaining_days // 30
            remaining_days = remaining_days - months_count * 30
        days_count = remaining_days

    charged_month_days = months_count * 26
    free_week_days = weeks_count
    if free_week_days > 3:
        free_week_days = 3
    charged_week_days = weeks_count * 7 - free_week_days
    charged_days_total = charged_month_days + charged_week_days + days_count

    total_amount = round(charged_days_total * daily_price, 2)
    breakdown_lines = _breakdown_to_lines(
        daily_price=daily_price,
        months_count=months_count,
        weeks_count=weeks_count,
        days_count=days_count,
    )

    return {
        "days": days_total,
        "total": total_amount,
        "breakdown": breakdown_lines,
    }


def quote_total(
    start_date: date, end_date: date, rate_table: RateTable
) -> Dict[str, Any]:
    """Quote a rental from start to end using the configured rate table.

    Behavior:
        - Returns zeroed values for invalid ranges (missing dates or end <= start).
        - Uses `rate_table.day` as the daily price (coerced via `_safe_float`).
        - Computes both month-first and week-first packings; returns the cheaper.
        - Includes a line-item breakdown and the currency.

    Args:
        start_date: Inclusive rental start date.
        end_date: Exclusive rental end date.
        rate_table: Rates/currency container (may be None; defaults handled).

    Returns:
        Dict with keys:
            - "days": total rental days
            - "total": final charge (float, rounded to 2 decimals)
            - "breakdown": list of month/week/day lines
            - "currency": currency code (e.g., "EUR")
    """
    if start_date is None or end_date is None:
        return {
            "days": 0,
            "total": 0.0,
            "breakdown": [],
            "currency": rate_table.currency if rate_table is not None else "EUR",
        }
    if end_date <= start_date:
        return {
            "days": 0,
            "total": 0.0,
            "breakdown": [],
            "currency": rate_table.currency if rate_table is not None else "EUR",
        }

    if rate_table is None:
        currency_value = "EUR"
        daily_price_value = 0.0
    else:
        currency_value = rate_table.currency
        daily_price_value = _safe_float(getattr(rate_table, "day", None))

    if daily_price_value <= 0.0:
        return {
            "days": 0,
            "total": 0.0,
            "breakdown": [],
            "currency": currency_value,
        }

    total_days = (end_date - start_date).days

    month_first_cost = _cost_for(total_days, daily_price_value, month_first=True)
    week_first_cost = _cost_for(total_days, daily_price_value, month_first=False)

    if month_first_cost["total"] <= week_first_cost["total"]:
        best_cost = month_first_cost
    else:
        best_cost = week_first_cost

    result: Dict[str, Any] = {
        "days": best_cost["days"],
        "total": best_cost["total"],
        "breakdown": best_cost["breakdown"],
        "currency": currency_value,
    }
    return result
