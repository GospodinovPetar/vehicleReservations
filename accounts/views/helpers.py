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
    """
    Return the mutable session dict that stores email-code state; create if missing.

    Session structure (per purpose):
        {
          PURPOSE: {
            'email': str,
            'hash': str,           # HMAC of email:purpose:code
            'expires_at': int,     # epoch seconds
            'attempts': int,       # failed attempts
            'ttl_minutes': int
          },
          ...
        }
    """
    return request.session.setdefault(SESSION_KEY, {})


def _hash_code(email: str, purpose: str, code: str) -> str:
    """
    Build a stable HMAC for a given email/purpose/code bundle.

    Args:
        email: Email address being verified.
        purpose: Logical purpose key (e.g., 'register' or 'reset_pwd').
        code: The plaintext verification code.

    Returns:
        str: Hex digest HMAC.
    """
    msg = f"{email}:{purpose}:{code}"
    return salted_hmac("email-code", msg).hexdigest()


def _issue_code(request, *, email: str, purpose: str, ttl_minutes: int = 10):
    """
    Generate a new code, store its HMAC and metadata in session, and return it.

    Side effects:
        - Writes to `request.session[SESSION_KEY][purpose]`
        - Marks session as modified

    Args:
        email: Target email to associate with the code.
        purpose: Purpose namespace (e.g., PURPOSE_REGISTER).
        ttl_minutes: Validity window in minutes.

    Returns:
        tuple[str, int]: (plaintext code, ttl_minutes)
    """
    code = secrets.token_hex(4).upper()
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
    """
    Remove any in-progress code bundle for a given purpose from the session.

    Args:
        purpose: Purpose namespace to clear.
    """
    state = _codes_state(request)
    if purpose in state:
        del state[purpose]
        request.session.modified = True


def _validate_code(request, *, email: str, purpose: str, submitted_code: str):
    """
    Validate a user-submitted code against the stored session bundle.

    - Enforces email match, expiry, and an attempt limit.
    - Consumes and clears the bundle on success or on certain failures.

    Args:
        email: Email to validate against the stored bundle.
        purpose: Purpose namespace of the flow.
        submitted_code: User-entered code (case-insensitive).

    Returns:
        tuple[bool, str|None]: (is_valid, error_message_if_any)
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
        bundle["attempts"] = int(bundle.get("attempts", 0)) + 1
        request.session.modified = True
        return False, "Invalid code."

    _consume_and_clear(request, purpose)
    return True, None


def _send_verification_email(to_email: str, code: str, ttl_minutes: int):
    """
    Email the registration verification code.

    Args:
        to_email: Recipient email.
        code: Plaintext verification code.
        ttl_minutes: Minutes until expiration (for informing the user).
    """
    subject = "Your verification code"
    body = (
        "Hi,\n\n"
        "Use this code to verify your email:\n\n"
        f"{code}\n\n"
        f"It expires in {ttl_minutes} minutes.\n"
    )
    send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [to_email])


def _send_reset_email(to_email: str, code: str, ttl_minutes: int):
    """
    Email the password reset code.

    Args:
        to_email: Recipient email.
        code: Plaintext reset code.
        ttl_minutes: Minutes until expiration (for informing the user).
    """
    subject = "Your password reset code"
    body = (
        "Hi,\n\n"
        "Use this code to reset your password:\n\n"
        f"{code}\n\n"
        f"It expires in {ttl_minutes} minutes.\n"
    )
    send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [to_email])
