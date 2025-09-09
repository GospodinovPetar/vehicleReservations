from django import forms
from django.contrib.auth.forms import UserCreationForm
from inventory.models import User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "password1", "password2")  # no role selection for normal signup

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "user"  # default role for self-registrations
        if commit:
            user.save()
        return user
