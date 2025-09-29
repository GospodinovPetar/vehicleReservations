from __future__ import annotations

from typing import Iterable, List, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


__all__ = [
    "user_group_name",
    "role_groups_for_user",
    "broadcast_reservation_event",
]


# ---------------------------------------------------------------------------
# Group naming helpers (used by ReservationConsumer and optional in views)
# ---------------------------------------------------------------------------

def user_group_name(user_id: Optional[int]) -> str:
    """
    Return a stable per-user Channels group name.
    Your consumer calls this with user.id (may be None for anon).
    """
    return f"user.{user_id if user_id is not None else 'anon'}"


def role_groups_for_user(user) -> List[str]:
    """
    Map Django user -> role-based Channels group names.
    Extend this to your RBAC scheme as needed.
    """
    groups: List[str] = []
    try:
        # Example: staff users get a manager-like role group
        if getattr(user, "is_staff", False):
            groups.append("role.manager")

        # Include all Django auth group names as role.<groupname>
        if hasattr(user, "groups"):
            try:
                groups.extend([f"role.{g.name}" for g in user.groups.all()])
            except Exception:
                # If querying groups fails, ignore quietly
                pass
    except Exception:
        # If 'user' is AnonymousUser or lacks attrs, just return what we have
        pass
    return groups


# ---------------------------------------------------------------------------
# Broadcaster (call from signals/views to publish WS events)
# ---------------------------------------------------------------------------

def broadcast_reservation_event(
    event: str,
    reservation_dict: dict,
    audience: Iterable[str],
) -> None:
    """
    Publish a reservation-related event to one or more Channels groups.

    Parameters
    ----------
    event : str
        Logical event name, e.g. "reservation.created", "reservation.updated",
        "reservation.deleted", "group.status_changed", etc.
    reservation_dict : dict
        JSON-serializable payload describing the reservation/group change.
        If you include "modified_by_id" or "created_by_id", that user id will
        be surfaced to the consumer as actor_user_id.
    audience : Iterable[str]
        List/iterable of Channels group names to fanout to. For a global stream,
        include "reservations.all" (your consumer joins this on connect).

    Notes
    -----
    - This sends a Channels message with "type": "reservation.event", which
      routes to ReservationConsumer.reservation_event(self, event).
    - The consumer simply relays this structure to the client.
    """
    layer = get_channel_layer()
    if layer is None:
        # Channels not configured; fail silently (or raise if you prefer)
        return

    base_payload = {
        "type": "reservation.event",  # <-- consumer handler name
        "event": event,
        "reservation": reservation_dict,
        # Convenience field: consumer forwards this to the client
        "actor_user_id": reservation_dict.get("modified_by_id")
                          or reservation_dict.get("created_by_id"),
    }

    for group in audience:
        # Attach the target group so the client can see which group delivered it
        message = {**base_payload, "group": group}
        async_to_sync(layer.group_send)(group, message)
