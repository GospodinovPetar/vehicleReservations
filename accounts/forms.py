from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

# Imports from inventory app
from inventory.models.vehicle import Vehicle, VehicleType, EngineType
from inventory.models.reservation import (
    VehicleReservation,
    ReservationStatus,
    Location,
    ReservationGroup,
)

CustomUser = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    """Form for user self-registration (default role = user)."""

    first_name = forms.CharField(required=True, label="First Name")
    last_name = forms.CharField(required=True, label="Last Name")
    phone = forms.CharField(required=True, label="Phone")

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "email", "first_name", "last_name", "phone", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "user"  # default role for self-registrations
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.phone = self.cleaned_data["phone"]
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    """Form for users to update their profile (not role/blocked fields)."""

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "email", "phone"]


class UserEditForm(forms.ModelForm):
    """
    Admin edit form for users (no password fields).
    Admins cannot edit other admins (enforced in view).
    """

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone",
            "is_blocked",
        ]


class VehicleForm(forms.ModelForm):
    """
    Vehicle form:
    - car_type & engine_type use TextChoices from the model
    - available pickup/dropoff locations required (ModelMultipleChoice)
    """

    car_type = forms.ChoiceField(choices=VehicleType.choices, label="Car Type")
    engine_type = forms.ChoiceField(choices=EngineType.choices, label="Engine Type")

    available_pickup_locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=True,
        widget=forms.SelectMultiple,
        label="Pick-up Location",
    )
    available_return_locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=True,
        widget=forms.SelectMultiple,
        label="Drop-off Location",
    )

    class Meta:
        model = Vehicle
        fields = [
            "name",
            "car_type",
            "engine_type",
            "seats",
            "price_per_day",
            "available_pickup_locations",
            "available_return_locations",
            "plate_number",
        ]


class ReservationStatusForm(forms.ModelForm):
    class Meta:
        model = ReservationGroup
        fields = ["status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = ReservationStatus.choices

class EmailCodeForm(forms.Form):
    email = forms.EmailField()
    code = forms.CharField(max_length=32, label="Code")


class EmailOnlyForm(forms.Form):
    email = forms.EmailField()


class PasswordResetConfirmForm(forms.Form):
    email = forms.EmailField(label="Email")
    code = forms.CharField(max_length=32, label="Code from email")
    new_password = forms.CharField(widget=forms.PasswordInput(), min_length=8, label="New password")
    new_password_confirm = forms.CharField(widget=forms.PasswordInput(), min_length=8, label="Confirm new password")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("new_password_confirm"):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned
