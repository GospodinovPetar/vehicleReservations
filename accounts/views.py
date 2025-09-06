from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.shortcuts import render, redirect

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("inventory:home")
    else:
        form = UserCreationForm()
    return render(request, "accounts/auth.html", {"form": form, "title": "Register"})

def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.GET.get("next") or "inventory:home"
            return redirect(next_url)
    else:
        form = AuthenticationForm(request)
    return render(request, "accounts/auth.html", {"form": form, "title": "Login"})

def logout_view(request):
    logout(request)
    return redirect("inventory:home")
