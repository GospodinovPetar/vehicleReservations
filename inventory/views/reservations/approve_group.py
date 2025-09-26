from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from inventory.views.services.status_switch import transition_group, TransitionError


@user_passes_test(lambda u: u.is_staff)
@require_http_methods(["POST"])
def approve_group(request, group_id: int):
    try:
        grp = transition_group(group_id=group_id, action="approve", actor=request.user)
    except TransitionError as e:
        messages.info(request, str(e))
    except Exception as e:
        messages.error(request, str(e))
    else:
        messages.success(
            request,
            f"Reservation {grp.reference} approved. Awaiting payment.",
        )
    return redirect("inventory:reservations")
