from datetime import date
from decimal import Decimal


def parse_iso_date(value):
    """Return a date from YYYY-MM-DD string or None on error."""
    try:
        if value:
            return date.fromisoformat(value)
        return None
    except Exception:
        return None


def compute_total(days_count, price_per_day):
    """Pricing: total = days × daily price."""
    if price_per_day is None:
        return Decimal("0.00")
    daily = Decimal(str(price_per_day))
    total = daily * Decimal(int(days_count))
    return total.quantize(Decimal("0.01"))
