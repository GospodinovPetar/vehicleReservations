from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
def register(request):
    """
    Register a new user with Django's built-in UserCreationForm.
    On success, log the user in and redirect to the inventory home page.
    """
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            login(request, new_user)
            messages.success(request, "Your account has been created and you are now logged in.")
            return redirect("inventory:home")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserCreationForm()

    context = {
        "form": form,
        "title": "Register",
    }
    return render(request, "accounts/auth.html", context)


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Log an existing user in using AuthenticationForm.
    Respects an optional ?next=/some/path redirect.
    """
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.GET.get("next")
            if not next_url:
                next_url = "inventory:home"
            messages.success(request, "You are now logged in.")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)

    context = {
        "form": form,
        "title": "Login",
    }
    return render(request, "accounts/auth.html", context)


@require_http_methods(["POST", "GET"])
def logout_view(request):
    """
    Log the current user out and send them to the home page.
    """
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("inventory:home")
