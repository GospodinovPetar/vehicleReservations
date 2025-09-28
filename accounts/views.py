from django.contrib import messages
from django.db import models
from django.http import HttpResponseForbidden
from django.contrib.auth import login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.utils.crypto import salted_hmac
import secrets
import time

# Inventory models
from inventory.models.vehicle import Vehicle
from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    Location,
    ReservationGroup,
)

from .forms import (
    CustomUserCreationForm,
    UserEditForm,
    VehicleForm,
    ReservationStatusForm,
    UserProfileForm,
    # Email-code forms
    EmailCodeForm,
    EmailOnlyForm,
    PasswordResetConfirmForm,
)

from .models import PendingRegistration

User = get_user_model()


# --------------- Session-backed code helpers (NO DB for codes) ---------------

SESSION_KEY = "email_codes"  # maps purposes to code bundles
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


# ----------- Auth views -----------
@require_http_methods(["GET", "POST"])
def register(request):
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

            # Save pending (24h)
            PendingRegistration.start(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                password_hash=make_password(raw_password),
                ttl_hours=24,
            )

            # Issue & email code (session only; no DB)
            code, ttl = _issue_code(request, email=email, purpose=PURPOSE_REGISTER, ttl_minutes=10)
            _send_verification_email(email, code, ttl)

            request.session["pending_verify_email"] = email
            messages.success(request, "We sent a verification code to your email. Complete verification to create your account.")
            return redirect("accounts:verify-email")
        messages.error(request, "Please correct the errors below.")
    else:
        form = CustomUserCreationForm()

    return render(request, "accounts/auth/auth.html", {"form": form, "title": "Register"})


@require_http_methods(["GET", "POST"])
def verify_email(request):
    """
    Verify email with code:
    - GET: if session contains a pending email, re-issue a new code and email it.
    - POST: validate against session; if OK, create the real user from PendingRegistration and log in.
    """
    initial = {"email": request.session.get("pending_verify_email", "")}

    if request.method == "GET":
        email = initial.get("email") or ""
        if email:
            pending = PendingRegistration.objects.filter(email=email).order_by("-created_at").first()
            if pending:
                if pending.is_expired():
                    pending.delete()
                    request.session.pop("pending_verify_email", None)
                    messages.error(request, "Your pending registration expired. Please register again.")
                    return redirect("accounts:register")
                # Always re-issue a new session code on GET
                code, ttl = _issue_code(request, email=email, purpose=PURPOSE_REGISTER, ttl_minutes=10)
                _send_verification_email(email, code, ttl)
                messages.info(request, "We emailed you a new verification code.")
        form = EmailCodeForm(initial=initial)
        return render(request, "accounts/auth/auth.html", {"form": form, "title": "Verify Email"})

    # POST
    form = EmailCodeForm(request.POST)
    if form.is_valid():
        email = form.cleaned_data["email"].strip()
        code = form.cleaned_data["code"].strip().upper()

        ok, err = _validate_code(request, email=email, purpose=PURPOSE_REGISTER, submitted_code=code)
        if not ok:
            # auto re-issue a fresh code
            fresh_code, ttl = _issue_code(request, email=email, purpose=PURPOSE_REGISTER, ttl_minutes=10)
            _send_verification_email(email, fresh_code, ttl)
            messages.error(request, f"{err} A new code has been sent.")
            return render(request, "accounts/auth/auth.html", {"form": EmailCodeForm(initial={"email": email}), "title": "Verify Email"})

        # Find pending registration
        pending = PendingRegistration.objects.filter(email=email).order_by("-created_at").first()
        if not pending or pending.is_expired():
            if pending and pending.is_expired():
                pending.delete()
            messages.error(request, "No pending registration found or it has expired. Please register again.")
            return redirect("accounts:register")

        # Create the actual user
        user = User(
            username=pending.username,
            email=pending.email,
            first_name=pending.first_name,
            last_name=pending.last_name,
            role=pending.role or "user",
            phone=pending.phone,
            is_active=True,
        )
        user.password = pending.password_hash  # hashed
        user.save()

        # Cleanup & login
        pending.delete()
        request.session.pop("pending_verify_email", None)
        messages.success(request, "Email verified. Your account has been created and you are now logged in.")
        login(request, user)
        return redirect("/")

    return render(request, "accounts/auth/auth.html", {"form": form, "title": "Verify Email"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Normal login.
    EXTRA: If auth fails, check for a matching PendingRegistration (username OR email)
    with matching password; if found, redirect to verify page and re-issue/send the code there.
    """
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Blocked or inactive users cannot log in
            if user.is_blocked or not user.is_active:
                messages.error(
                    request,
                    "Your account has been blocked or is inactive. Please contact support.",
                )
                return redirect("accounts:login")

            login(request, user)
            messages.success(request, "You are now logged in.")

            if user.role == "admin":
                return redirect("accounts:admin-dashboard")
            elif user.role == "manager":
                return redirect("accounts:manager-dashboard")
            else:
                return redirect("/")
        else:
            username_or_email = request.POST.get("username", "").strip()
            raw_password = request.POST.get("password", "")

            pending = (
                PendingRegistration.objects.filter(
                    models.Q(username=username_or_email) | models.Q(email=username_or_email)
                )
                .order_by("-created_at")
                .first()
            )
            if pending:
                if pending.is_expired():
                    pending.delete()
                    messages.error(request, "Your pending registration expired. Please register again.")
                    return redirect("accounts:register")

                if check_password(raw_password, pending.password_hash):
                    request.session["pending_verify_email"] = pending.email
                    # re-issue code immediately so they don't need to reload
                    code, ttl = _issue_code(request, email=pending.email, purpose=PURPOSE_REGISTER, ttl_minutes=10)
                    _send_verification_email(pending.email, code, ttl)
                    messages.info(request, "Finish setting up your account. We’ve emailed you a new verification code.")
                    return redirect("accounts:verify-email")

            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)

    return render(request, "accounts/auth/auth.html", {"form": form, "title": "Login"})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


@login_required
def profile_detail(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    return render(request, "accounts/profile_detail.html", {"user": user})


@login_required
def profile_view(request, pk=None):
    """
    Show user profile.
    - /profile/ → always show the logged-in user
    - /profile/<pk>/ →
        * if pk == request.user.pk → show own profile
        * if admin/manager → show target user's profile
        * else → forbidden
    """
    if pk is None:
        # No pk provided → always current user
        profile_user = request.user
    else:
        if pk == request.user.pk:
            profile_user = request.user
        elif request.user.role in ["admin", "manager"]:
            profile_user = get_object_or_404(User, pk=pk)
        else:
            return HttpResponseForbidden("You cannot view other users’ profiles.")

    # Fetch reservations for this profile
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
def profile_change_password(request):
    """Allow logged-in user to change their password."""
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

    return render(request, "accounts/profile/profile_change_password.html", {"form": form})


# ----------- Password reset (session code, no DB) -----------
@require_http_methods(["GET", "POST"])
def forgot_password_start(request):
    """
    Ask for email; if a profile exists, issue a session-backed code and email it,
    then push to confirm screen. (Neutral response to avoid enumeration.)
    """
    if request.method == "POST":
        form = EmailOnlyForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip()
            if User.objects.filter(email=email).exists():
                code, ttl = _issue_code(request, email=email, purpose=PURPOSE_RESET, ttl_minutes=10)
                _send_reset_email(email, code, ttl)
            messages.info(request, "If that email exists, we’ve sent a code.")
            return redirect("accounts:forgot-password-confirm")
    else:
        form = EmailOnlyForm()
    return render(request, "accounts/auth/auth.html", {"form": form, "title": "Forgot Password"})


@require_http_methods(["GET", "POST"])
def forgot_password_confirm(request):
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

            ok, err = _validate_code(request, email=email, purpose=PURPOSE_RESET, submitted_code=code)
            if not ok:
                # auto re-issue
                fresh, ttl = _issue_code(request, email=email, purpose=PURPOSE_RESET, ttl_minutes=10)
                _send_reset_email(email, fresh, ttl)
                messages.error(request, f"{err} A new code has been sent.")
                return render(request, "accounts/auth/auth.html", {"form": PasswordResetConfirmForm(), "title": "Reset Password"})

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, "No user account found for this email.")
                return render(request, "accounts/auth/auth.html", {"form": form, "title": "Reset Password"})

            user.set_password(new_password)
            user.save(update_fields=["password"])
            messages.success(request, "Your password was updated. You can log in now.")
            return redirect("accounts:login")
    else:
        # Visiting the page directly: no auto-issue (we don't know email yet).
        form = PasswordResetConfirmForm()

    return render(request, "accounts/auth/auth.html", {"form": form, "title": "Reset Password"})


# ----------- Admin decorators / views -----------
def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.role == "admin")(
        view_func
    )


@admin_required
def admin_dashboard(request):
    query = request.GET.get("q")
    role_filter = request.GET.get("role")
    status_filter = request.GET.get("status")

    users = User.objects.all().order_by("-date_joined")

    if query:
        users = users.filter(username__icontains=query) | users.filter(
            email__icontains=query
        )
    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter == "blocked":
        users = users.filter(is_blocked=True)
    elif status_filter == "active":
        users = users.filter(is_blocked=False)

    stats = {
        "total": User.objects.count(),
        "admins": User.objects.filter(role="admin").count(),
        "managers": User.objects.filter(role="manager").count(),
        "users": User.objects.filter(role="user").count(),
        "blocked": User.objects.filter(is_blocked=True).count(),
    }

    return render(
        request, "accounts/admin/admin_dashboard.html", {"users": users, "stats": stats}
    )


@admin_required
def block_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    # Strict: do not allow any admin-to-admin actions
    if user.role == "admin":
        messages.error(request, "You cannot block another admin.")
    else:
        user.is_blocked = True
        user.save()
        messages.success(request, f"{user.username} has been blocked.")
    return redirect("accounts:admin-dashboard")


@admin_required
def unblock_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot modify another admin.")
    else:
        user.is_blocked = False
        user.save()
        messages.success(request, f"{user.username} has been unblocked.")
    return redirect("accounts:admin-dashboard")


@admin_required
def promote_manager(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot modify another admin.")
    else:
        user.role = "manager"
        user.save()
        messages.success(request, f"{user.username} is now a manager.")
    return redirect("accounts:admin-dashboard")


@admin_required
def demote_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot modify another admin.")
    else:
        user.role = "user"
        user.save()
        messages.success(request, f"{user.username} is now a regular user.")
    return redirect("accounts:admin-dashboard")


@admin_required
def create_user(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "User created successfully.")
            return redirect("accounts:admin-dashboard")
    else:
        form = CustomUserCreationForm()
    return render(
        request,
        "accounts/admin/admin_user_form.html",
        {"form": form, "title": "Create User"},
    )


@admin_required
def edit_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    # Do not allow admin to edit other admins
    if user.role == "admin":
        messages.error(request, "You cannot edit another admin.")
        return redirect("accounts:admin-dashboard")

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            # Save with no password change
            form.save()
            messages.success(request, "User updated successfully.")
            return redirect("accounts:admin-dashboard")
    else:
        form = UserEditForm(instance=user)
    return render(
        request,
        "accounts/admin/admin_user_form.html",
        {"form": form, "title": f"Edit {user.username}"},
    )


@admin_required
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.role == "admin":
        messages.error(request, "You cannot delete another admin.")
        return redirect("accounts:admin-dashboard")

    if request.method == "POST":
        user.delete()
        messages.success(request, "User deleted successfully.")
        return redirect("accounts:admin-dashboard")
    return render(
        request, "accounts/admin/admin_user_confirm_delete.html", {"user": user}
    )


# ----------- Manager decorators / views -----------
def manager_required(view_func):
    return user_passes_test(
        lambda u: u.is_authenticated and u.role in ["manager", "admin"],
        login_url="/accounts/login/",
    )(view_func)


@manager_required
def manager_dashboard(request):
    return render(request, "accounts/manager/manager_dashboard.html")


@manager_required
def manager_vehicles(request):
    vehicles = Vehicle.objects.all()
    return render(
        request, "accounts/manager/manager_vehicles.html", {"vehicles": vehicles}
    )


@manager_required
def manager_reservations(request):
    # managers/admins see all reservations
    reservations = VehicleReservation.objects.all().select_related(
        "user", "vehicle", "pickup_location", "return_location"
    )
    return render(
        request,
        "accounts/reservations/reservation_list.html",
        {"reservations": reservations},
    )


# --- VEHICLE VIEWS ---
@manager_required
def vehicle_list(request):
    vehicles = Vehicle.objects.all()
    return render(request, "accounts/vehicle_list.html", {"vehicles": vehicles})


def vehicle_create(request):
    pickup_param = request.GET.get("pickup")

    initial = {}
    if pickup_param:
        try:
            loc = Location.objects.filter(pk=int(pickup_param)).only("id").first()
            if loc:
                initial["available_pickup_locations"] = loc.pk
        except (TypeError, ValueError):
            pass

    form = VehicleForm(request.POST or None, initial=initial, request=request)

    if request.method == "POST":
        if form.is_valid():
            vehicle = form.save()
            request.session["last_pickup_id"] = form.cleaned_data["available_pickup_locations"].pk
            messages.success(request, "Vehicle created successfully.")
            return redirect("accounts:vehicle-list")
        else:
            messages.error(request, "Please fix the errors below.")

    return render(request, "accounts/manager/vehicle_form.html", {"form": form})


@manager_required
def vehicle_edit(request, pk):
    vehicle = Vehicle.objects.get(pk=pk)

    if request.method == "POST":
        form = VehicleForm(request.POST, instance=vehicle)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.save()

            pickup = form.cleaned_data.get("available_pickup_locations")
            if pickup:
                vehicle.available_pickup_locations.set([pickup])
            else:
                vehicle.available_pickup_locations.clear()

            dropoffs = form.cleaned_data.get("available_return_locations")
            if dropoffs:
                vehicle.available_return_locations.set(dropoffs)
            else:
                vehicle.available_return_locations.clear()

            messages.success(request, "Vehicle updated successfully.")
            return redirect("accounts:vehicle-list")
    else:
        form = VehicleForm(instance=vehicle)

    return render(
        request,
        "accounts/vehicles/vehicle_form.html",
        {"form": form},
    )


def vehicle_delete(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)

    if vehicle.reservations.filter(group__status__in=ReservationStatus.blocking()).exists():
        messages.error(request, "This vehicle is part of an ongoing reservation and cannot be deleted.")
        return redirect("accounts:vehicle-list")

    vehicle.delete()
    messages.success(request, "Vehicle deleted successfully.")
    return redirect("accounts:vehicle-list")


# --- RESERVATION VIEWS ---
@manager_required
def reservation_list(request):
    """
    Managers/admins see groups split into:
    - ongoing: PENDING, AWAITING_PAYMENT, RESERVED
    - archived: COMPLETED, REJECTED, CANCELED
    """
    ongoing = (
        ReservationGroup.objects.filter(
            status__in=[
                ReservationStatus.PENDING,
                ReservationStatus.AWAITING_PAYMENT,
                ReservationStatus.RESERVED,
            ]
        )
        .prefetch_related("reservations__vehicle", "reservations__user")
        .order_by("-created_at")
    )

    archived = (
        ReservationGroup.objects.filter(
            status__in=[
                ReservationStatus.COMPLETED,
                ReservationStatus.REJECTED,
                ReservationStatus.CANCELED,
            ]
        )
        .prefetch_related("reservations__vehicle", "reservations__user")
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/reservations/reservation_list.html",
        {"ongoing": ongoing, "archived": archived},
    )


@manager_required
def reservation_group_approve(request, pk):
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.PENDING:
        return HttpResponseForbidden("Only pending groups can be approved.")

    group.status = ReservationStatus.AWAITING_PAYMENT
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} is now awaiting payment.")
    return redirect("accounts:reservation-list")


@manager_required
def reservation_group_reject(request, pk):
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status not in (
            ReservationStatus.PENDING,
            ReservationStatus.AWAITING_PAYMENT,
    ):
        return HttpResponseForbidden(
            "Only pending/awaiting-payment groups can be rejected."
        )

    group.status = ReservationStatus.REJECTED
    group.save(update_fields=["status"])

    messages.warning(request, f"Reservation group {group.id} has been rejected.")
    return redirect("accounts:reservation-list")


@manager_required
def reservation_update(request, pk):
    """Update a group’s status instead of individual reservations."""
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.PENDING:
        return HttpResponseForbidden("Only pending groups can be updated.")

    if request.method == "POST":
        form = ReservationStatusForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, f"Reservation group {group.id} updated.")
            return redirect("accounts:reservation-list")
    else:
        form = ReservationStatusForm(instance=group)

    return render(
        request,
        "accounts/reservations/reservation_update.html",
        {"form": form, "group": group},
    )


@manager_required
def reservation_approve(request, pk):
    reservation = get_object_or_404(VehicleReservation, pk=pk)
    grp = reservation.group
    if not grp or grp.status != ReservationStatus.PENDING:
        return HttpResponseForbidden("Only pending reservation groups can be approved.")

    grp.status = ReservationStatus.AWAITING_PAYMENT
    grp.save(update_fields=["status"])

    messages.success(request, f"Reservation #{reservation.id} is now awaiting payment.")
    return redirect("accounts:reservation-list")


@manager_required
def reservation_reject(request, pk):
    r = get_object_or_404(VehicleReservation, pk=pk)
    grp = r.group
    if not grp or grp.status not in (
            ReservationStatus.PENDING,
            ReservationStatus.AWAITING_PAYMENT,
    ):
        return HttpResponseForbidden(
            "Only pending/awaiting-payment reservation groups can be rejected."
        )

    grp.status = ReservationStatus.REJECTED
    grp.save(update_fields=["status"])

    messages.warning(request, f"Reservation #{r.id} rejected; group moved to Rejected.")
    return redirect("accounts:reservation-list")


@manager_required
def reservation_cancel(request, pk):
    r = get_object_or_404(VehicleReservation, pk=pk)
    grp = r.group
    if not grp or grp.status != ReservationStatus.RESERVED:
        return HttpResponseForbidden(
            "Only reserved reservation groups can be canceled."
        )

    grp.status = ReservationStatus.CANCELED
    grp.save(update_fields=["status"])

    messages.warning(request, f"Reservation #{r.id} canceled; group moved to Canceled.")
    return redirect("accounts:reservation-list")


@manager_required
def reservation_complete(request, pk):
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.RESERVED:
        return HttpResponseForbidden("Only reserved groups can be marked as completed.")

    group.status = ReservationStatus.COMPLETED
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} marked as Completed.")
    return redirect("accounts:reservation-list")


@manager_required
def reservation_group_complete(request, pk):
    group = get_object_or_404(ReservationGroup, pk=pk)
    if group.status != ReservationStatus.RESERVED:
        return HttpResponseForbidden("Only reserved groups can be marked as completed.")

    group.status = ReservationStatus.COMPLETED
    group.save(update_fields=["status"])

    messages.success(request, f"Reservation group {group.id} marked as Completed.")
    return redirect("accounts:reservation-list")


# --- User reservation view (normal users only) ---
@login_required
def user_reservations(request):
    reservations = (
        VehicleReservation.objects.filter(user=request.user)
        .select_related("vehicle", "pickup_location", "return_location")
        .all()
    )
    return render(
        request,
        "accounts/reservations/reservation_list_user.html",
        {"reservations": reservations},
    )


# --- LOCATION MANAGEMENT (accessible to admin + manager) ---
@manager_required
def location_list(request):
    locations = Location.objects.all()
    return render(
        request, "accounts/locations/location_list.html", {"locations": locations}
    )


@manager_required
def location_create(request):
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            Location.objects.create(name=name)
            messages.success(request, "Location created.")
            return redirect("accounts:location-list")
        messages.error(request, "Please provide a name.")
    return render(
        request, "accounts/locations/location_form.html", {"title": "Create location"}
    )


@manager_required
def location_edit(request, pk):
    loc = get_object_or_404(Location, pk=pk)
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            loc.name = name
            loc.save()
            messages.success(request, "Location updated.")
            return redirect("accounts:location-list")
        messages.error(request, "Please provide a name.")
    return render(
        request,
        "accounts/locations/location_form.html",
        {"location": loc, "title": "Edit location"},
    )


@manager_required
def location_delete(request, pk):
    loc = get_object_or_404(Location, pk=pk)

    from inventory.models.reservation import VehicleReservation as VR
    has_blocking = VR.objects.filter(
        group__status__in=ReservationStatus.blocking()
    ).filter(
        models.Q(pickup_location=loc) | models.Q(return_location=loc)
    ).exists()

    if has_blocking:
        messages.error(
            request,
            "This location is used by an ongoing reservation and cannot be deleted."
        )
        return redirect("accounts:location-list")

    loc.delete()
    messages.success(request, "Location deleted successfully.")
    return redirect("accounts:location-list")
