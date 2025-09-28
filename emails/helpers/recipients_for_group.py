def recipients_for_group(group) -> list[str]:
    user = getattr(group, "user", None)
    email = getattr(user, "email", None) if user else None
    return [email] if email else []
