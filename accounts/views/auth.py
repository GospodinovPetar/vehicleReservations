from django.contrib.auth import login, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.hashers import make_password, check_password
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db import models

from accounts.forms import (
    CustomUserCreationForm,
    EmailCodeForm,
    UserProfileForm,
    EmailOnlyForm,
    PasswordResetConfirmForm,
)
from accounts.models import PendingRegistration
from accounts.views.helpers import (
    _issue_code,
    PURPOSE_REGISTER,
    _send_verification_email,
    _validate_code,
    PURPOSE_RESET,
    _send_reset_email,
    User,
)

from inventory.models.reservation import VehicleReservation

SESSION_KEY = "email_codes"


@require_http_methods(["GET", "POST"])
def register(request):
    """
    Start a registration with email verification.

    - POST: Valid form creates a PendingRegistration (24h TTL), issues a code,
      emails it, stores email in session, and redirects to verify step.
    - GET: Renders the registration form.

    Renders:
        accounts/auth/auth.html (title="Register")
    """
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            first_name = form.cleaned_data.get("first_name", "")
            last_name = form.cleaned_data.get("last_name", "")
            phone = form.cleaned_data.get("phone", "")
            raw_password = form.cleaned_data["password1"]

            PendingRegistration.start(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                password_hash=make_password(raw_password),
                ttl_hours=24,
            )

            code, ttl = _issue_code(
                request, email=email, purpose=PURPOSE_REGISTER, ttl_minutes=10
            )
            _send_verification_email(email, code, ttl)

            request.session["pending_verify_email"] = email
            messages.success(
                request,
                "We sent a verification code to your email. Complete verification to create your account.",
            )
            return redirect("accounts:verify-email")
        messages.error(request, "Please correct the errors below.")
    else:
        form = CustomUserCreationForm()

    return render(
        request, "accounts/auth/auth.html", {"form": form, "title": "Register"}
    )


@require_http_methods(["GET", "POST"])
def verify_email(request):
    """
    Complete registration by verifying email with a code.

    - GET: If a pending registration exists for the session email, re-issues a code
      and informs the user; then renders the code-entry form.
    - POST: Validates the submitted code; on success creates and logs in the user.

    Renders:
        accounts/auth/auth.html (title="Verify Email")
    """
    initial = {"email": request.session.get("pending_verify_email", "")}

    if request.method == "GET":
        email = initial.get("email") or ""
        if email:
            pending = (
                PendingRegistration.objects.filter(email=email)
                .order_by("-created_at")
                .first()
            )
            if pending:
                if pending.is_expired():
                    pending.delete()
                    request.session.pop("pending_verify_email", None)
                    messages.error(
                        request,
                        "Your pending registration expired. Please register again.",
                    )
                    return redirect("accounts:register")
                code, ttl = _issue_code(
                    request, email=email, purpose=PURPOSE_REGISTER, ttl_minutes=10
                )
                _send_verification_email(email, code, ttl)
                messages.info(request, "We emailed you a new verification code.")
        form = EmailCodeForm(initial=initial)
        return render(
            request, "accounts/auth/auth.html", {"form": form, "title": "Verify Email"}
        )

    form = EmailCodeForm(request.POST)
    if form.is_valid():
        email = form.cleaned_data["email"].strip()
        code = form.cleaned_data["code"].strip().upper()

        ok, err = _validate_code(
            request, email=email, purpose=PURPOSE_REGISTER, submitted_code=code
        )
        if not ok:
            fresh_code, ttl = _issue_code(
                request, email=email, purpose=PURPOSE_REGISTER, ttl_minutes=10
            )
            _send_verification_email(email, fresh_code, ttl)
            messages.error(request, f"{err} A new code has been sent.")
            return render(
                request,
                "accounts/auth/auth.html",
                {
                    "form": EmailCodeForm(initial={"email": email}),
                    "title": "Verify Email",
                },
            )

        pending = (
            PendingRegistration.objects.filter(email=email)
            .order_by("-created_at")
            .first()
        )
        if not pending or pending.is_expired():
            if pending and pending.is_expired():
                pending.delete()
            messages.error(
                request,
                "No pending registration found or it has expired. Please register again.",
            )
            return redirect("accounts:register")

        user = User(
            username=pending.username,
            email=pending.email,
            first_name=pending.first_name,
            last_name=pending.last_name,
            role=pending.role or "user",
            phone=pending.phone,
            is_active=True,
        )
        user.password = pending.password_hash
        user.save()

        pending.delete()
        request.session.pop("pending_verify_email", None)
        messages.success(
            request,
            "Email verified. Your account has been created and you are now logged in.",
        )
        login(request, user)
        return redirect("/")

    return render(
        request, "accounts/auth/auth.html", {"form": form, "title": "Verify Email"}
    )


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Authenticate and log a user in.

    - POST: Valid credentials log the user in and redirect based on role
      (admin → admin dashboard, manager → manager dashboard, else home).
      If login fails but a matching PendingRegistration exists and password matches,
      the flow redirects to email verification and re-issues a code.
    - GET: Render the login form.

    Renders:
        accounts/auth/auth.html (title="Login")
    """
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if getattr(user, "is_blocked", False) or not user.is_active:
                messages.error(
                    request,
                    "Your account has been blocked or is inactive. Please contact support.",
                )
                return redirect("accounts:login")

            login(request, user)
            messages.success(request, "You are now logged in.")

            if getattr(user, "role", "user") == "admin":
                return redirect("accounts:admin-dashboard")
            elif getattr(user, "role", "user") == "manager":
                return redirect("accounts:manager-dashboard")
            else:
                return redirect("/")
        else:
            username_or_email = request.POST.get("username", "").strip()
            raw_password = request.POST.get("password", "")

            pending = (
                PendingRegistration.objects.filter(
                    models.Q(username=username_or_email)
                    | models.Q(email=username_or_email)
                )
                .order_by("-created_at")
                .first()
            )
            if pending:
                if pending.is_expired():
                    pending.delete()
                    messages.error(
                        request,
                        "Your pending registration expired. Please register again.",
                    )
                    return redirect("accounts:register")

                if check_password(raw_password, pending.password_hash):
                    request.session["pending_verify_email"] = pending.email
                    # re-issue code immediately so they don't need to reload
                    code, ttl = _issue_code(
                        request,
                        email=pending.email,
                        purpose=PURPOSE_REGISTER,
                        ttl_minutes=10,
                    )
                    _send_verification_email(pending.email, code, ttl)
                    messages.info(
                        request,
                        "Finish setting up your account. We’ve emailed you a new verification code.",
                    )
                    return redirect("accounts:verify-email")

            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)

    return render(request, "accounts/auth/auth.html", {"form": form, "title": "Login"})


def logout_view(request):
    """
    Log out the current user and redirect home.

    Side effects:
        - Clears the authenticated session.
        - Flashes a success message.
    """
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


@login_required
def profile_detail(request, pk):
    """
    View a user's profile detail page.

    Access:
        - Self
        - Admin/Manager can view any user by pk.

    Args:
        pk (int): User primary key.

    Renders:
        accounts/profile_detail.html
    """
    user = get_object_or_404(User, pk=pk)
    return render(request, "accounts/profile_detail.html", {"user": user})


@login_required
def profile_view(request, pk=None):
    """
    View a profile page and the user's reservations.

    - If pk is omitted or equals the current user's pk, shows own profile.
    - Admins/managers can view any user's profile; others are forbidden.

    Args:
        pk (int|None): Optional user primary key.

    Renders:
        accounts/profile/profile_detail.html
    """
    if pk is None:
        profile_user = request.user
    else:
        if pk == request.user.pk:
            profile_user = request.user
        elif getattr(request.user, "role", "user") in ["admin", "manager"]:
            profile_user = get_object_or_404(User, pk=pk)
        else:
            return HttpResponseForbidden("You cannot view other users’ profiles.")

    reservations = VehicleReservation.objects.filter(user=profile_user).select_related(
        "vehicle", "pickup_location", "return_location"
    )

    return render(
        request,
        "accounts/profile/profile_detail.html",
        {"profile_user": profile_user, "reservations": reservations},
    )


@login_required
def profile_edit(request):
    """
    Allow the logged-in user to edit their own profile.

    - GET: Render profile edit form with current data.
    - POST: Validate and save; redirect to profile detail on success.
    """
    user = request.user
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile-detail", pk=user.id)
    else:
        form = UserProfileForm(instance=user)

    return render(request, "accounts/profile/profile_edit.html", {"form": form})


@login_required
def profile_change_password(request):
    """
    Let the logged-in user change their password.

    - GET: Render password change form.
    - POST: Validate and update password, keeping the session authenticated.
    """
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            messages.success(request, "Your password has been updated successfully.")
            return redirect("accounts:profile")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PasswordChangeForm(user=request.user)

    return render(
        request, "accounts/profile/profile_change_password.html", {"form": form}
    )


# ----------- Password reset (session code, no DB) -----------
@require_http_methods(["GET", "POST"])
def forgot_password_start(request):
    """
    Start a password reset by email (no account enumeration).

    - POST: If a user exists for the email, issue a session-backed code and email it.
      Always respond with a neutral info message and redirect to confirm step.
    - GET: Render email collection form.

    Renders:
        accounts/auth/auth.html (title="Forgot Password")
    """
    if request.method == "POST":
        form = EmailOnlyForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip()
            if User.objects.filter(email=email).exists():
                code, ttl = _issue_code(
                    request, email=email, purpose=PURPOSE_RESET, ttl_minutes=10
                )
                _send_reset_email(email, code, ttl)
            messages.info(request, "If that email exists, we’ve sent a code.")
            return redirect("accounts:forgot-password-confirm")
    else:
        form = EmailOnlyForm()
    return render(
        request, "accounts/auth/auth.html", {"form": form, "title": "Forgot Password"}
    )


@require_http_methods(["GET", "POST"])
def forgot_password_confirm(request):
    """
    Confirm password reset with email + code + new password.

    - POST: Validate code against session bundle; on success update the password.
      If invalid/expired/too many attempts, automatically re-issue a new code.
    - GET: Render the confirmation form.

    Renders:
        accounts/auth/auth.html (title="Reset Password")
    """
    if request.method == "POST":
        form = PasswordResetConfirmForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip()
            code = form.cleaned_data["code"].strip().upper()
            new_password = form.cleaned_data["new_password"]

            ok, err = _validate_code(
                request, email=email, purpose=PURPOSE_RESET, submitted_code=code
            )
            if not ok:
                # auto re-issue
                fresh, ttl = _issue_code(
                    request, email=email, purpose=PURPOSE_RESET, ttl_minutes=10
                )
                _send_reset_email(email, fresh, ttl)
                messages.error(request, f"{err} A new code has been sent.")
                return render(
                    request,
                    "accounts/auth/auth.html",
                    {"form": PasswordResetConfirmForm(), "title": "Reset Password"},
                )

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, "No user account found for this email.")
                return render(
                    request,
                    "accounts/auth/auth.html",
                    {"form": form, "title": "Reset Password"},
                )

            user.set_password(new_password)
            user.save(update_fields=["password"])
            messages.success(request, "Your password was updated. You can log in now.")
            return redirect("accounts:login")
    else:
        form = PasswordResetConfirmForm()

    return render(
        request, "accounts/auth/auth.html", {"form": form, "title": "Reset Password"}
    )
