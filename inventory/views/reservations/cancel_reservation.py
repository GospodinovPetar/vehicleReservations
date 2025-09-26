from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from inventory.views.services.status_switch import transition_group, TransitionError


@login_required
@require_http_methods(["POST"])
def cancel_reservation(request, group_id: int):
    try:
        grp = transition_group(group_id=group_id, action="cancel", actor=request.user)
    except TransitionError as e:
        messages.info(request, str(e))
    except Exception as e:
        messages.error(request, str(e))
    else:
        messages.info(request, f"Reservation {grp.reference} canceled.")
    return redirect("inventory:reservations")
