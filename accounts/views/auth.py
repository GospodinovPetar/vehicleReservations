from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.forms import (
    CustomUserCreationForm,
    EmailCodeForm,
    EmailOnlyForm,
    PasswordResetConfirmForm,
    UserProfileForm,
)
from accounts.models import PendingRegistration
from accounts.views.helpers import (
    PURPOSE_REGISTER,
    PURPOSE_RESET,
    User,
    _issue_code,
    _send_reset_email,
    _send_verification_email,
    _validate_code,
)
from inventory.models.reservation import VehicleReservation

SESSION_KEY = "email_codes"


@require_http_methods(["GET", "POST"])
def register(request: HttpRequest) -> HttpResponse:
    """
    Registration:
    - Do NOT create CustomUser yet.
    - Store data in PendingRegistration (DB) with hashed password.
    - Issue a session-backed code and email it.
    - Redirect to verify page.
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
def verify_email(request: HttpRequest) -> HttpResponse:
    """
    Verify email with code:
    - GET: if session contains a pending email, re-issue a new code and email it.
    - POST: validate against session; if OK, create the real user from PendingRegistration and log in.
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
def login_view(request: HttpRequest) -> HttpResponse:
    """
    Normal login.
    EXTRA: If auth fails, check for a matching PendingRegistration (username OR email)
    with matching password; if found, redirect to verify page and re-issue/send the code there.
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


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


@login_required
def profile_detail(request: HttpRequest, pk: int) -> HttpResponse:
    user = get_object_or_404(User, pk=pk)
    return render(request, "accounts/profile/profile_detail.html", {"user": user})


@login_required
def profile_view(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """
    Show user profile.
    - /profile/ → always show the logged-in user
    - /profile/<pk>/ →
        * if pk == request.user.pk → show own profile
        * if admin/manager → show target user's profile
        * else → forbidden
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
def profile_edit(request: HttpRequest) -> HttpResponse:
    """Allow a logged-in user to edit their own profile."""
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
def profile_change_password(request: HttpRequest) -> HttpResponse:
    """Allow logged-in user to change their password."""
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password has been updated successfully.")
            return redirect("accounts:profile")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PasswordChangeForm(user=request.user)

    return render(
        request, "accounts/profile/profile_change_password.html", {"form": form}
    )


@require_http_methods(["GET", "POST"])
def forgot_password_start(request: HttpRequest) -> HttpResponse:
    """
    Ask for email; if a profile exists, issue a session-backed code and email it,
    then push to confirm screen. (Neutral response to avoid enumeration.)
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
def forgot_password_confirm(request: HttpRequest) -> HttpResponse:
    """
    Email + code + new password; validate against session bundle and update password.
    If invalid/expired/too many attempts, auto-issue a fresh one and show the form again.
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
