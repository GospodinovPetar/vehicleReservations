from __future__ import annotations

from typing import Any, Iterable, List, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


__all__ = [
    "user_group_name",
    "role_groups_for_user",
    "broadcast_reservation_event",
]


def user_group_name(user_id: Optional[int]) -> str:
    return f"user.{user_id if user_id is not None else 'anon'}"


def role_groups_for_user(user: Any) -> List[str]:
    groups: List[str] = []
    try:
        if getattr(user, "is_staff", False):
            groups.append("role.manager")
        if hasattr(user, "groups"):
            try:
                groups.extend([f"role.{g.name}" for g in user.groups.all()])
            except Exception:
                pass
    except Exception:
        pass
    return groups


def broadcast_reservation_event(
    event: str,
    reservation_dict: dict[str, Any],
    audience: Iterable[str],
) -> None:
    layer = get_channel_layer()
    if layer is None:
        return

    base_payload = {
        "type": "reservation.event",
        "event": event,
        "reservation": reservation_dict,
        "actor_user_id": reservation_dict.get("modified_by_id")
        or reservation_dict.get("created_by_id"),
    }

    for group in audience:
        async_to_sync(layer.group_send)(group, {**base_payload, "group": group})
