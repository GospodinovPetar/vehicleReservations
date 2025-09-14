from _datetime import date


def parse_iso_date(value):
    try:
        if value:
            return date.fromisoformat(value)
        return None
    except Exception:
        return None
