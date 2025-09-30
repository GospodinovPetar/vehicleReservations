from datetime import date


def parse_iso_date(value):
    """
    Parse a YYYY-MM-DD string into a `datetime.date`.

    Args:
        value: String like "2025-09-30" (or any falsy value).

    Returns:
        date | None: Parsed date on success, otherwise None.
    """
    try:
        if value:
            return date.fromisoformat(value)
        return None
    except Exception:
        return None
