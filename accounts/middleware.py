from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class BlockedUserMiddleware:
    """
    Logs out blocked users automatically if they are authenticated
    and marked as blocked.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.is_blocked:
            from django.contrib.auth import logout
            logout(request)
            messages.error(request, "Your account has been blocked.")
            return redirect(reverse("accounts:blocked"))  # redirect to blocked page
        return self.get_response(request)
