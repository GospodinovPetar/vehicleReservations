from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List, Any


@dataclass
class RateTable:
    day: Optional[float] = None
    week: Optional[float] = None
    month: Optional[float] = None
    currency: str = "EUR"


def _safe_float(value: Any) -> float:
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
