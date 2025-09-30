from django.shortcuts import redirect


def redirect_back_to_search(start_str: str | None, end_str: str | None):
    """
    Redirect to the search page, preserving start/end query parameters.

    Args:
        start_str: Start date string (e.g., "2025-09-30") or None.
        end_str: End date string (e.g., "2025-10-02") or None.

    Returns:
        HttpResponseRedirect: Redirect to `/search/?start=...&end=...`.
    """
    start_q = start_str or ""
    end_q = end_str or ""
    return redirect(f"/search/?start={start_q}&end={end_q}")
