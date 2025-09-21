from django.shortcuts import redirect


def redirect_back_to_search(start_str: str | None, end_str: str | None):
    start_q = start_str or ""
    end_q = end_str or ""
    return redirect(f"/search/?start={start_q}&end={end_q}")
