from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict, List, Tuple

DAY = 1
WEEK = 7
MONTH = 30

@dataclass
class RateTable:
    day: Optional[float] = None
    week: Optional[float] = None
    month: Optional[float] = None
    currency: str = "EUR"


def _breakdown_sort_key(item: Dict[str, float]) -> int:
    """Sort by month > week > day."""
    sort_order = {"month": 3, "week": 2, "day": 1}
    period = item.get("period", "")
    return sort_order.get(period, 0)


def calculate_minimum_cost(number_of_days: int, rate_table: RateTable) -> Tuple[float, List[Dict[str, float]]]:
    """
    Dynamic programming: for each day count up to number_of_days,
    pick the cheapest combination of day/week/month rates.
    """
    very_large_number = 10 ** 15

    # minimum_cost_up_to_day[d] is the minimum total cost to cover d days
    minimum_cost_up_to_day: List[float] = [0.0]
    day_index = 0
    while day_index < number_of_days:
        minimum_cost_up_to_day.append(float(very_large_number))
        day_index += 1

    # selected_choice_for_day[d] remembers which period we used to reach the minimum at day d
    selected_choice_for_day: List[Optional[Tuple[str, int, float]]] = []
    index = 0
    while index <= number_of_days:
        selected_choice_for_day.append(None)
        index += 1

    # Determine available choices from the rate table
    available_choices: List[Tuple[str, int, float]] = []
    if rate_table.day is not None:
        available_choices.append(("day", DAY, float(rate_table.day)))
    if rate_table.week is not None:
        available_choices.append(("week", WEEK, float(rate_table.week)))
    if rate_table.month is not None:
        available_choices.append(("month", MONTH, float(rate_table.month)))

    if len(available_choices) == 0:
        raise ValueError("No rates configured.")

    # Fill DP table
    current_day = 1
    while current_day <= number_of_days:
        choice_index = 0
        while choice_index < len(available_choices):
            period_label, period_length_days, period_unit_price = available_choices[choice_index]
            previous_day_index = current_day - period_length_days
            if previous_day_index < 0:
                previous_day_index = 0

            candidate_cost = minimum_cost_up_to_day[previous_day_index] + period_unit_price
            if candidate_cost < minimum_cost_up_to_day[current_day]:
                minimum_cost_up_to_day[current_day] = candidate_cost
                selected_choice_for_day[current_day] = (period_label, period_length_days, period_unit_price)

            choice_index += 1
        current_day += 1

    # Reconstruct breakdown
    breakdown_by_period: Dict[str, Dict[str, float]] = {}
    remaining_days = number_of_days
    while remaining_days > 0:
        choice_tuple = selected_choice_for_day[remaining_days]
        if choice_tuple is None:
            # Should not happen if choices exist; safety check
            break
        period_label, period_length_days, period_unit_price = choice_tuple

        if period_label not in breakdown_by_period:
            breakdown_by_period[period_label] = {"units": 0, "unit_amount": period_unit_price}

        breakdown_by_period[period_label]["units"] = breakdown_by_period[period_label]["units"] + 1
        remaining_days = remaining_days - period_length_days

    # Convert breakdown dict to a stable, sorted list
    breakdown_list: List[Dict[str, float]] = []
    for period_label in breakdown_by_period:
        info = breakdown_by_period[period_label]
        units_int = int(info["units"])
        unit_amount_rounded = round(float(info["unit_amount"]), 2)
        subtotal_value = units_int * float(info["unit_amount"])
        subtotal_rounded = round(subtotal_value, 2)

        item = {
            "period": period_label,
            "units": units_int,
            "unit_amount": unit_amount_rounded,
            "subtotal": subtotal_rounded,
        }
        breakdown_list.append(item)

    breakdown_list.sort(key=_breakdown_sort_key, reverse=True)

    total_cost_rounded = round(minimum_cost_up_to_day[number_of_days], 2)
    return total_cost_rounded, breakdown_list


def quote_total(start_date: date, end_date: date, rate_table: RateTable) -> Dict[str, object]:
    """
    Public API: returns the number of days, total price, breakdown, and currency.
    """
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    total_days = (end_date - start_date).days
    total_cost, breakdown_list = calculate_minimum_cost(total_days, rate_table)

    result: Dict[str, object] = {}
    result["days"] = total_days
    result["total"] = total_cost
    result["breakdown"] = breakdown_list
    result["currency"] = rate_table.currency
    return result
