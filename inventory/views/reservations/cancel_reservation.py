from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from inventory.views.services.status_switch import transition_group, TransitionError


@login_required
@require_http_methods(["POST"])
def cancel_reservation(request: HttpRequest, group_id: int) -> HttpResponse:
    try:
        group = transition_group(group_id=group_id, action="cancel", actor=request.user)
    except TransitionError as exc:
        messages.info(request, str(exc))
    except Exception as exc:
        messages.error(request, str(exc))
    else:
        reference_value = getattr(group, "reference", None) or str(
            getattr(group, "pk", "")
        )
        messages.info(request, f"Reservation {reference_value} canceled.")
    return redirect("inventory:reservations")
