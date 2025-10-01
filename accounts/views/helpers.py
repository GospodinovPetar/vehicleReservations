from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Dict, Tuple

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone

from emails.send_emails import send_verification_email, send_reset_password_email

User = get_user_model()

SESSION_KEY = "email_codes"
PURPOSE_REGISTER = "register"
PURPOSE_RESET = "reset_pwd"


def _get_bundle(request: HttpRequest) -> Dict[str, dict]:
    return request.session.setdefault(SESSION_KEY, {})


def _issue_code(request: HttpRequest, email: str, purpose: str, ttl_minutes: int) -> Tuple[str, int]:
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
    return code, int(ttl_minutes)


def _consume_and_clear(request: HttpRequest, purpose: str) -> None:
    bundle = _get_bundle(request)
    if purpose in bundle:
        del bundle[purpose]
        request.session.modified = True


def _validate_code(
    request: HttpRequest,
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

    try:
        issued_at = datetime.fromisoformat(stored["issued_at"])
        if timezone.is_naive(issued_at):
            issued_at = timezone.make_aware(issued_at, timezone.get_current_timezone())
    except Exception:
        _consume_and_clear(request, purpose)
        return False, "Verification expired. Please request a new code."

    ttl = int(stored.get("ttl", 15))
    if timezone.now() > issued_at + timedelta(minutes=ttl):
        _consume_and_clear(request, purpose)
        return False, "Verification code expired. Please request a new one."

    if stored.get("code") != submitted_code:
        stored["attempts"] = int(stored.get("attempts", 0)) + 1
        request.session.modified = True
        return False, "Invalid code."

    _consume_and_clear(request, purpose)
    return True, None


def _send_verification_email(to_email: str, code: str, ttl_minutes: int) -> None:
    """
    Send the registration verification code at most once per (email, code) within TTL.
    Uses Django cache as the primary idempotency lock; falls back to a per-request
    guard only if the cache call itself fails. Never retries a possibly-sent email
    inside this function.
    """
    email_norm = to_email.strip().lower()
    key = f"idemp:verify:{email_norm}:{code}"
    timeout = max(60, int(ttl_minutes) * 60)

    should_send = False

    try:
        should_send = cache.add(key, 1, timeout=timeout)
    except Exception:
        bundle = _get_bundle(getattr(_send_verification_email, "_request", object()))
        if isinstance(bundle, dict) and not bundle.get(key):
            bundle[key] = True
            should_send = True
        else:
            should_send = False

    if not should_send:
        return

    try:
        send_verification_email(to_email, code, ttl_minutes)
    except Exception:
        # log the error, metrics, etc. but don't resend here
        # logger.exception("Verification email send failed for %s (code=%s)", email_norm, code)
        raise


def _send_reset_email(to_email: str, code: str, ttl_minutes: int) -> None:
    """Send the password reset code exactly once per (email, code) within TTL."""
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
