from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.utils.crypto import salted_hmac
import secrets
import time


User = get_user_model()


SESSION_KEY = "email_codes"
PURPOSE_REGISTER = "register"
PURPOSE_RESET = "reset_pwd"


def _codes_state(request) -> dict:
    return request.session.setdefault(SESSION_KEY, {})


def _hash_code(email: str, purpose: str, code: str) -> str:
    # HMAC using Django SECRET_KEY; avoids storing plaintext code in session
    msg = f"{email}:{purpose}:{code}"
    return salted_hmac("email-code", msg).hexdigest()


def _issue_code(request, *, email: str, purpose: str, ttl_minutes: int = 10):
    """
    Generate an 8-hex code, store only its hash + expiry + attempts in the session.
    """
    code = secrets.token_hex(4).upper()  # e.g. '9F42A1C8'
    expires_at = int(time.time()) + ttl_minutes * 60
    state = _codes_state(request)
    state[purpose] = {
        "email": email,
        "hash": _hash_code(email, purpose, code),
        "expires_at": expires_at,
        "attempts": 0,
        "ttl_minutes": ttl_minutes,
    }
    request.session.modified = True
    return code, ttl_minutes


def _consume_and_clear(request, purpose: str):
    state = _codes_state(request)
    if purpose in state:
        del state[purpose]
        request.session.modified = True


def _validate_code(request, *, email: str, purpose: str, submitted_code: str):
    """
    Check presence, email match, expiry, attempts < 5, and HMAC equality.
    Returns (ok: bool, error_message: str | None).
    """
    state = _codes_state(request)
    bundle = state.get(purpose)
    if not bundle:
        return False, "No code in progress. Please request a new code."

    if bundle.get("email", "").lower() != email.lower():
        return False, "Email does not match the ongoing verification."

    now = int(time.time())
    if now > int(bundle.get("expires_at", 0)):
        _consume_and_clear(request, purpose)
        return False, "Code expired. We sent you a new one."

    if int(bundle.get("attempts", 0)) >= 5:
        _consume_and_clear(request, purpose)
        return False, "Too many attempts. We sent you a new code."

    expected_hash = bundle.get("hash")
    if expected_hash != _hash_code(email, purpose, submitted_code.strip().upper()):
        # bump attempts
        bundle["attempts"] = int(bundle.get("attempts", 0)) + 1
        request.session.modified = True
        return False, "Invalid code."

    # success -> clear
    _consume_and_clear(request, purpose)
    return True, None


# ----------- Mail helpers -----------
def _send_verification_email(to_email: str, code: str, ttl_minutes: int):
    subject = "Your verification code"
    body = (
        "Hi,\n\n"
        "Use this code to verify your email:\n\n"
        f"{code}\n\n"
        f"It expires in {ttl_minutes} minutes.\n"
    )
    send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [to_email])


def _send_reset_email(to_email: str, code: str, ttl_minutes: int):
    subject = "Your password reset code"
    body = (
        "Hi,\n\n"
        "Use this code to reset your password:\n\n"
        f"{code}\n\n"
        f"It expires in {ttl_minutes} minutes.\n"
    )
    send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [to_email])
