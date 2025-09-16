from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser
from inventory.models.vehicle import Vehicle
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
    class Meta:
        model = Vehicle
        fields = ["name", "car_type", "seats", "price_per_day", "pickup_location", "dropoff_location"]

    car_type = forms.ChoiceField(choices=Vehicle.CarType.choices)  # uses TextChoices

    pickup_location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        required=True,
        label="Pick-up Location"
    )
    dropoff_location = forms.ModelChoiceField(
        queryset=Location.objects.all(),
        required=True,
        label="Drop-off Location"
    )


class ReservationStatusForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit choices to manager-friendly statuses
        self.fields["status"].choices = [
            (ReservationStatus.RESERVED, "Reserved"),
            (ReservationStatus.AWAITING_PICKUP, "Awaiting Pickup"),
            (ReservationStatus.CONFIRMED, "Confirmed"),
            (ReservationStatus.REJECTED, "Rejected"),
            (ReservationStatus.CANCELLED, "Cancelled"),
        ]
