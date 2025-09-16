from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser
from inventory.models.vehicle import Vehicle, VehicleType, EngineType, Location
from inventory.models.reservation import Reservation, ReservationStatus, Location
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    """Form for user self-registration (default role = user)."""

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "user"  # default role for self-registrations
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    """
    Admin edit form for users (no password fields).
    """

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role", "phone", "is_blocked"]


class VehicleForm(forms.ModelForm):
    car_type = forms.ChoiceField(choices=VehicleType.choices, label="Car Type")
    engine_type = forms.ChoiceField(choices=EngineType.choices, label="Engine Type")

    available_pickup_locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="Available Pick-up Locations",
    )
    available_return_locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="Available Drop-off Locations",
    )

    class Meta:
        model = Vehicle
        fields = [
            "name",
            "car_type",
            "engine_type",
            "seats",
            "unlimited_seats",
            "price_per_day",
            "available_pickup_locations",
            "available_return_locations",
        ]


class ReservationStatusForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (ReservationStatus.RESERVED, "Reserved"),
            (ReservationStatus.AWAITING_PICKUP, "Awaiting Pickup"),
            (ReservationStatus.CONFIRMED, "Confirmed"),
            (ReservationStatus.REJECTED, "Rejected"),
            (ReservationStatus.CANCELLED, "Cancelled"),
        ]
