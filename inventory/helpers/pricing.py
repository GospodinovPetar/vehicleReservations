from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List


@dataclass
class RateTable:
    day: Optional[float] = None
    week: Optional[float] = None  # ignored
    month: Optional[float] = None  # ignored
    currency: str = "EUR"


def _safe_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def quote_total(
    start_date: date, end_date: date, rate_table: RateTable
) -> Dict[str, object]:
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    total_days = (end_date - start_date).days

    daily_price = 0.0
    if rate_table is not None and rate_table.day is not None:
        daily_price = _safe_float(rate_table.day)

    total_cost = round(daily_price * total_days, 2)

    breakdown: List[Dict[str, object]] = [
        {
            "period": "day",
            "units": int(total_days),
            "unit_amount": round(daily_price, 2),
            "subtotal": total_cost,
        }
    ]

    result: Dict[str, object] = {
        "days": int(total_days),
        "total": total_cost,
        "breakdown": breakdown,
        "currency": rate_table.currency if rate_table else "EUR",
    }
    return result
