from django.contrib import auth
from ninja.security import HttpBasicAuth


class BasicAuth(HttpBasicAuth):
    def authenticate(self, request, username, password):
        user = auth.authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            return None
        request.user = user
        return user
