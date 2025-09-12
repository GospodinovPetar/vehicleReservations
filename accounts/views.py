from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .forms import CustomUserCreationFormrom
from django.shortcuts import render


# ----------- Auth views -----------
@require_http_methods(["GET", "POST"])
def register(request):
    """User self-registration (role = user by default)."""
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            login(request, new_user)
            messages.success(request, "Your account was created and you are now logged in.")
            return redirect("/")
        messages.error(request, "Please correct the errors below.")
    else:
        form = CustomUserCreationForm()
    return render(request, "accounts/auth.html", {"form": form, "title": "Register"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Blocked users cannot log in
            if user.is_blocked:
                messages.error(request, "Your account has been blocked. Please contact support.")
                return redirect("accounts:login")

            login(request, user)
            next_url = request.GET.get("next") or "/"
            messages.success(request, "You are now logged in.")
            return redirect(next_url)
        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)
    return render(request, "auth.html", {"form": form, "title": "Login"})


def blocked_view(request):
    """Page shown to blocked users after logout."""
    return render(request, "accounts/blocked.html")


def logout_view(request):
    """Logout user."""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


# ----------- Dashboards -----------
def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_superuser, login_url="/")(view_func)


@superuser_required
def admin_dashboard(request):
    return render(request, "accounts/admin_dashboard.html")


def manager_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.role == "manager", login_url="/")(view_func)


@manager_required
def manager_dashboard(request):
    return render(request, "accounts/manager_dashboard.html")
