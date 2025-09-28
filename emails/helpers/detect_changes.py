from emails.send_vehicle_removed import FieldChange, format_value


def detect_changes(before, after) -> list[FieldChange]:
    tracked = [
        ("start_date", "Start date"),
        ("end_date", "End date"),
        ("pickup_location", "Pickup location"),
        ("return_location", "Return location"),
        ("vehicle", "Vehicle"),
    ]
    changes: list[FieldChange] = []
    for attr, label in tracked:
        b = getattr(before, attr, None)
        a = getattr(after, attr, None)
        if b != a:
            changes.append(
                FieldChange(
                    name=attr,
                    label=label,
                    before=format_value(b),
                    after=format_value(a),
                )
            )
    return changes
