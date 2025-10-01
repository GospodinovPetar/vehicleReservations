from __future__ import annotations

from functools import wraps
from typing import Callable, Dict

from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
    user_passes_test,
)
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import CustomUserCreationForm, UserEditForm
from accounts.views.helpers import User
from inventory.models.reservation import VehicleReservation
from inventory.models.vehicle import Vehicle



ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_USER = "user"


def _is_admin(user: User) -> bool:
    """Return True if the user is authenticated and has role='admin'."""
    return bool(user.is_authenticated and getattr(user, "role", ROLE_USER) == ROLE_ADMIN)


def _is_manager_or_admin(user: User) -> bool:
    """Return True if the user is authenticated and role is 'manager' or 'admin'."""
    role = getattr(user, "role", ROLE_USER)
    return bool(user.is_authenticated and role in {ROLE_MANAGER, ROLE_ADMIN})



def admin_required(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """
    Decorator ensuring the user is authenticated and has role='admin'.

    Usage:
        @login_required
        @admin_required
        def some_admin_view(...):
            ...
    """
    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        return user_passes_test(_is_admin)(view_func)(*args, **kwargs)

    return _wrapped


def manager_required(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """
    Decorator ensuring the user is authenticated and has role in {'manager','admin'}.

    Usage:
        @login_required
        @manager_required
        def some_manager_view(...):
            ...
    """
    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        return user_passes_test(
            _is_manager_or_admin, login_url="/accounts/login/"
        )(view_func)(*args, **kwargs)

    return _wrapped



@login_required
@admin_required
def admin_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Admin dashboard user listing with simple filtering.

    Query params:
        q (str): search by username or email (icontains).
        role (str): filter by exact role.
        status (str): 'blocked' or 'active'.

    Renders:
        accounts/admin/admin_dashboard.html

    Context:
        users (QuerySet[User])
        stats (dict): counts of roles and blocked/users.
    """
    query: str | None = request.GET.get("q")
    role_filter: str | None = request.GET.get("role")
    status_filter: str | None = request.GET.get("status")

    users: QuerySet[User] = User.objects.all().order_by("-date_joined")

    if query:
        query = query.strip()
        if query:
            users = users.filter(Q(username__icontains=query) | Q(email__icontains=query))

    if role_filter:
        users = users.filter(role=role_filter)

    if status_filter == "blocked":
        users = users.filter(is_blocked=True)
    elif status_filter == "active":
        users = users.filter(is_blocked=False)

    stats: Dict[str, int] = {
        "total": User.objects.count(),
        "admins": User.objects.filter(role=ROLE_ADMIN).count(),
        "managers": User.objects.filter(role=ROLE_MANAGER).count(),
        "users": User.objects.filter(role=ROLE_USER).count(),
        "blocked": User.objects.filter(is_blocked=True).count(),
    }

    return render(
        request,
        "accounts/admin/admin_dashboard.html",
        {"users": users, "stats": stats},
    )


@login_required
@admin_required
def block_user(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Block a user (except other admins).

    Args:
        pk (int): User primary key.

    Messages:
        - Error if target is admin.
        - Success when blocked.
    """
    user = get_object_or_404(User, pk=pk)
    if getattr(user, "role", ROLE_USER) == ROLE_ADMIN:
        messages.error(request, "You cannot block another admin.")
    else:
        user.is_blocked = True
        user.save()
        messages.success(request, f"{user.username} has been blocked.")
    return redirect("accounts:admin-dashboard")


@login_required
@admin_required
def unblock_user(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Unblock a user (except other admins).

    Args:
        pk (int): User primary key.
    """
    user = get_object_or_404(User, pk=pk)
    if getattr(user, "role", ROLE_USER) == ROLE_ADMIN:
        messages.error(request, "You cannot modify another admin.")
    else:
        user.is_blocked = False
        user.save()
        messages.success(request, f"{user.username} has been unblocked.")
    return redirect("accounts:admin-dashboard")


@login_required
@admin_required
def promote_manager(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Promote a user to manager (not allowed for admins).

    Args:
        pk (int): User primary key.
    """
    user = get_object_or_404(User, pk=pk)
    if getattr(user, "role", ROLE_USER) == ROLE_ADMIN:
        messages.error(request, "You cannot modify another admin.")
    else:
        user.role = ROLE_MANAGER
        user.save()
        messages.success(request, f"{user.username} is now a manager.")
    return redirect("accounts:admin-dashboard")


@login_required
@admin_required
def demote_user(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Demote a user to regular 'user' role (not allowed for admins).

    Args:
        pk (int): User primary key.
    """
    user = get_object_or_404(User, pk=pk)
    if getattr(user, "role", ROLE_USER) == ROLE_ADMIN:
        messages.error(request, "You cannot modify another admin.")
    else:
        user.role = ROLE_USER
        user.save()
        messages.success(request, f"{user.username} is now a regular user.")
    return redirect("accounts:admin-dashboard")


@login_required
@admin_required
def create_user(request: HttpRequest) -> HttpResponse:
    """
    Create a new user as an admin.

    - GET: Render creation form.
    - POST: Validate and save; redirect to dashboard on success.

    Renders:
        accounts/admin/admin_user_form.html
    """
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


@login_required
@admin_required
def edit_user(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Edit a user's basic fields (except password) as admin.

    - Disallows editing other admins.

    Args:
        pk (int): User primary key.

    Renders:
        accounts/admin/admin_user_form.html
    """
    user = get_object_or_404(User, pk=pk)

    # Do not allow admin to edit other admins
    if getattr(user, "role", ROLE_USER) == ROLE_ADMIN:
        messages.error(request, "You cannot edit another admin.")
        return redirect("accounts:admin-dashboard")

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
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


@login_required
@admin_required
def delete_user(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Delete a user (confirmation flow), not allowed for admins.

    - GET: Render confirm page.
    - POST: Delete and redirect to dashboard.

    Args:
        pk (int): User primary key.
    """
    user = get_object_or_404(User, pk=pk)

    if getattr(user, "role", ROLE_USER) == ROLE_ADMIN:
        messages.error(request, "You cannot delete another admin.")
        return redirect("accounts:admin-dashboard")

    if request.method == "POST":
        user.delete()
        messages.success(request, "User deleted successfully.")
        return redirect("accounts:admin-dashboard")

    return render(
        request,
        "accounts/admin/admin_user_confirm_delete.html",
        {"user": user},
    )



@login_required
@manager_required
def manager_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Render the manager dashboard landing page.

    Renders:
        accounts/manager/manager_dashboard.html
    """
    return render(request, "accounts/manager/manager_dashboard.html")


@login_required
@manager_required
def manager_vehicles(request: HttpRequest) -> HttpResponse:
    """
    Show all vehicles to managers/admins.

    Renders:
        accounts/manager/manager_vehicles.html

    Context:
        vehicles (QuerySet[Vehicle])
    """
    vehicles: QuerySet[Vehicle] = Vehicle.objects.all()
    return render(
        request,
        "accounts/manager/manager_vehicles.html",
        {"vehicles": vehicles},
    )


@login_required
@manager_required
@permission_required("inventory.view_reservationgroup", raise_exception=True)
def manager_reservations(request: HttpRequest) -> HttpResponse:
    """
    List all reservations for managers/admins.

    Renders:
        accounts/reservations/reservation_list.html

    Context:
        reservations (QuerySet[VehicleReservation])
    """
    # managers/admins see all reservations
    reservations: QuerySet[VehicleReservation] = (
        VehicleReservation.objects.all()
        .select_related("user", "vehicle", "pickup_location", "return_location")
    )
    return render(
        request,
        "accounts/reservations/reservation_list.html",
        {"reservations": reservations},
    )
