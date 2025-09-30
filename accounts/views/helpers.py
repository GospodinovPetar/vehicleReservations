from __future__ import annotations

from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache

import secrets
from typing import Tuple

User = get_user_model()

SESSION_KEY = "email_codes"
PURPOSE_REGISTER = "register"
PURPOSE_RESET = "reset_pwd"


def _get_bundle(request) -> dict:
    return request.session.setdefault(SESSION_KEY, {})


def _issue_code(request, email: str, purpose: str, ttl_minutes: int) -> Tuple[str, int]:
    """
    Issue a short-lived numeric code and stash it in the session.

    The structure in the session is:
      request.session[SESSION_KEY][purpose] = {
          "email": <email>,
          "code": <6-digit string>,
          "issued_at": <aware dt iso>,
          "ttl": <minutes>,
          "attempts": <int>
      }
    """
    code = f"{secrets.randbelow(1_000_000):06d}"

    bundle = _get_bundle(request)
    bundle[purpose] = {
        "email": email.strip().lower(),
        "code": code,
        "issued_at": timezone.now().isoformat(),
        "ttl": int(ttl_minutes),
        "attempts": 0,
    }
    request.session.modified = True
    # Keep backward compatibility: callers may expect (code, ttl)
    return code, int(ttl_minutes)


def _consume_and_clear(request, purpose: str) -> None:
    bundle = _get_bundle(request)
    if purpose in bundle:
        del bundle[purpose]
        request.session.modified = True


def _validate_code(
    request,
    purpose: str,
    email: str,
    submitted_code: str,
) -> Tuple[bool, str | None]:
    """
    Validate a code that was previously issued with _issue_code.

    Returns (is_valid, error_message). When valid, the stored code is consumed.
    """
    email = (email or "").strip().lower()
    submitted_code = (submitted_code or "").strip()

    bundle = _get_bundle(request)
    stored = bundle.get(purpose)
    if not stored:
        return False, "No verification in progress. Please request a new code."

    if stored.get("email") != email:
        return False, "This code was issued for a different email address."

    # Expiry check
    try:
        issued_at = timezone.datetime.fromisoformat(stored["issued_at"])
        if timezone.is_naive(issued_at):
            issued_at = timezone.make_aware(issued_at, timezone.get_current_timezone())
    except Exception:
        # If anything looks off, treat as expired to be safe
        _consume_and_clear(request, purpose)
        return False, "Verification expired. Please request a new code."

    ttl = int(stored.get("ttl", 15))
    if timezone.now() > issued_at + timezone.timedelta(minutes=ttl):
        _consume_and_clear(request, purpose)
        return False, "Verification code expired. Please request a new one."

    # Match check
    if stored.get("code") != submitted_code:
        stored["attempts"] = int(stored.get("attempts", 0)) + 1
        request.session.modified = True
        return False, "Invalid code."

    # Success — consume
    _consume_and_clear(request, purpose)
    return True, None


# === Email send helpers (FIX: single source of truth) ===
# Historically this module sent emails directly using django.core.mail.send_mail,
# while accounts/emails.py also sent the same email with HTML templates.
# That caused *duplicate emails* on registration.
#
# The fix is to delegate all sending to accounts.emails so only ONE code email
# is ever sent per issuance.


def _send_verification_email(to_email: str, code: str, ttl_minutes: int) -> None:
    """Send the registration verification code exactly once per (email, code) within TTL.

    Uses Django's cache as an idempotency lock so multiple call sites won't duplicate sends.
    """
    from accounts.emails import send_verification_email

    key = f"idemp:verify:{to_email.strip().lower()}:{code}"
    timeout = max(60, int(ttl_minutes) * 60)  # at least 60s, up to TTL
    try:
        # cache.add returns True only if the key did not exist
        if cache.add(key, 1, timeout=timeout):
            send_verification_email(to_email, code, ttl_minutes)
        else:
            # Duplicate detected; skip sending
            return
    except Exception:
        # If cache misconfigured, fall back to best-effort session guard
        # (still prevents duplicates in the same request cycle)
        _sent = _get_bundle(getattr(_send_verification_email, "_request", object()))
        if isinstance(_sent, dict) and not _sent.get(key):
            _sent[key] = True
            try:
                send_verification_email(to_email, code, ttl_minutes)
            finally:
                pass


def _send_reset_email(to_email: str, code: str, ttl_minutes: int) -> None:
    """Send the password reset code exactly once per (email, code) within TTL."""
    from accounts.emails import send_reset_password_email

    key = f"idemp:reset:{to_email.strip().lower()}:{code}"
    timeout = max(60, int(ttl_minutes) * 60)
    try:
        if cache.add(key, 1, timeout=timeout):
            send_reset_password_email(to_email, code, ttl_minutes)
        else:
            return
    except Exception:
        _sent = _get_bundle(getattr(_send_reset_email, "_request", object()))
        if isinstance(_sent, dict) and not _sent.get(key):
            _sent[key] = True
            try:
                send_reset_password_email(to_email, code, ttl_minutes)
            finally:
                pass
