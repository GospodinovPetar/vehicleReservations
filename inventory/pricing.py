from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List, Tuple

DAYS_IN_ONE_DAY = 1
DAYS_IN_ONE_WEEK = 7
DAYS_IN_ONE_MONTH = 30


@dataclass
class RateTable:
    """
    Price table:
    - day:   price for up to 1 day
    - week:  price for up to 7 days
    - month: price for up to 30 days
    """

    day: Optional[float] = None
    week: Optional[float] = None
    month: Optional[float] = None
    currency: str = "EUR"


def _period_priority(period_name: str) -> int:
    """
    Return a numeric priority for sorting the breakdown list.
    Higher means earlier in the list.
    """
    if period_name == "month":
        return 3
    if period_name == "week":
        return 2
    if period_name == "day":
        return 1
    return 0


def compute_minimum_cost_and_breakdown(
    total_days: int, rate_table: RateTable
) -> Tuple[float, List[Dict[str, float]]]:
    """
    Compute the minimum possible total cost to cover `total_days`, given the prices
    in `rate_table`. Also return a simple breakdown showing how many units of each
    period (day/week/month) were used in the optimal solution.

    Uses a straightforward dynamic programming approach:
      best_cost[d] = min over choices (best_cost[max(0, d - span)] + unit_price)
    """

    # Validate available period prices and collect them
    available_periods: List[Tuple[str, int, float]] = []
    if rate_table.day is not None:
        available_periods.append(("day", DAYS_IN_ONE_DAY, float(rate_table.day)))
    if rate_table.week is not None:
        available_periods.append(("week", DAYS_IN_ONE_WEEK, float(rate_table.week)))
    if rate_table.month is not None:
        available_periods.append(("month", DAYS_IN_ONE_MONTH, float(rate_table.month)))

    if len(available_periods) == 0:
        raise ValueError("No prices configured for this vehicle.")

    very_large_number = 10**15
    total_cost_by_day: List[float] = [0.0] + [very_large_number] * total_days
    choice_taken_by_day: List[Optional[Tuple[str, int, float]]] = [None] * (
        total_days + 1
    )

    # Compute best costs bottom-up
    current_day = 1
    while current_day <= total_days:
        for period_label, period_span_days, period_unit_price in available_periods:
            previous_index = current_day - period_span_days
            if previous_index < 0:
                previous_index = 0

            potential_cost = total_cost_by_day[previous_index] + period_unit_price
            if potential_cost < total_cost_by_day[current_day]:
                total_cost_by_day[current_day] = potential_cost
                choice_taken_by_day[current_day] = (
                    period_label,
                    period_span_days,
                    period_unit_price,
                )

        current_day += 1

    usage_breakdown: Dict[str, Dict[str, float]] = {}
    remaining_days = total_days
    while remaining_days > 0:
        chosen = choice_taken_by_day[remaining_days]
        if chosen is None:
            # Safety check: should not happen if inputs are valid
            break

        period_label, period_span_days, period_unit_price = chosen

        if period_label not in usage_breakdown:
            usage_breakdown[period_label] = {
                "units": 0,
                "unit_amount": period_unit_price,
            }

        period_record = usage_breakdown[period_label]
        period_record["units"] = float(int(period_record["units"]) + 1)
        period_record["unit_amount"] = float(period_unit_price)

        remaining_days = remaining_days - period_span_days

    # Convert the breakdown dictionary to a list of rows and sort visibly by size: month > week > day
    breakdown_rows: List[Dict[str, float]] = []
    for period_label in usage_breakdown:
        info = usage_breakdown[period_label]
        units_count = int(info["units"])
        unit_amount_value = float(info["unit_amount"])
        subtotal_value = float(units_count * unit_amount_value)

        row = {
            "period": period_label,
            "units": units_count,
            "unit_amount": round(unit_amount_value, 2),
            "subtotal": round(subtotal_value, 2),
        }
        breakdown_rows.append(row)

    # Sort descending by period priority (month first)
    index_i = 0
    while index_i < len(breakdown_rows) - 1:
        index_j = index_i + 1
        while index_j < len(breakdown_rows):
            left_priority = _period_priority(str(breakdown_rows[index_i].get("period")))
            right_priority = _period_priority(
                str(breakdown_rows[index_j].get("period"))
            )
            if right_priority > left_priority:
                temp_row = breakdown_rows[index_i]
                breakdown_rows[index_i] = breakdown_rows[index_j]
                breakdown_rows[index_j] = temp_row
            index_j += 1
        index_i += 1

    minimum_total_cost = round(float(total_cost_by_day[total_days]), 2)
    return minimum_total_cost, breakdown_rows


def quote_total(
    start_date: date, end_date: date, rate_table: RateTable
) -> Dict[str, object]:
    """
    Public function: given start/end dates and a rate table, return a quote dict:
      {
        "days": <int>,
        "total": <float>,
        "breakdown": <list of rows>,
        "currency": <str>,
      }
    """
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    total_days = (end_date - start_date).days
    minimum_total_cost, breakdown_rows = compute_minimum_cost_and_breakdown(
        total_days, rate_table
    )

    result: Dict[str, object] = {
        "days": total_days,
        "total": minimum_total_cost,
        "breakdown": breakdown_rows,
        "currency": rate_table.currency,
    }
    return result
