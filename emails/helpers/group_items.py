from typing import Iterable


def group_items(group) -> Iterable:
    return group.reservations.select_related(
        "vehicle", "pickup_location", "return_location", "user"
    ).all()
