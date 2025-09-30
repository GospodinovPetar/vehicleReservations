from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from mockpay.models import PaymentIntent


def _eur_amount(intent: PaymentIntent) -> str:
    """
    Format a PaymentIntent's integer cent amount as an EUR string.

    Args:
        intent: PaymentIntent with an `amount` field in cents (int).

    Returns:
        str: Formatted amount like "12.34".
    """
    cents_value = int(getattr(intent, "amount", 0) or 0)
    euros_part = cents_value // 100
    cents_part = cents_value % 100
    return f"{euros_part}.{cents_part:02d}"


def _cd(data: dict, *keys: str, default: str = "") -> str:
    """
    Return the first non-empty value from `data` among `keys`, else `default`.

    Treats None and empty-string as empty.

    Args:
        data: Mapping to read from.
        *keys: Keys to check in order.
        default: Fallback value if none of the keys has a non-empty value.

    Returns:
        str: The first non-empty value or the default.
    """
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _q2(value: Optional[Decimal]) -> Decimal:
    """
    Quantize a Decimal to two fractional digits using ROUND_HALF_UP.

    Args:
        value: Amount to quantize; None is treated as Decimal("0").

    Returns:
        Decimal: Quantized value with exactly two decimal places.
    """
    if value is None:
        value = Decimal("0")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_cents(value: Optional[Decimal]) -> int:
    """
    Convert a Decimal amount to integer cents with two-decimal rounding.

    Args:
        value: Decimal amount; None treated as 0.

    Returns:
        int: Amount in cents.
    """
    quantized = _q2(value or Decimal("0"))
    cents = (quantized * 100).to_integral_value(rounding=ROUND_HALF_UP)
    return int(cents)
