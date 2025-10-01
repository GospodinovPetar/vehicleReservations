from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from inventory.models.reservation import Location, ReservationGroup, ReservationStatus
from inventory.models.vehicle import EngineType, Vehicle, VehicleType

CustomUser = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    """Form for user self-registration (default role = user)."""

    first_name = forms.CharField(required=True, label="First Name")
    last_name = forms.CharField(required=True, label="Last Name")
    phone = forms.CharField(required=True, label="Phone")

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "password1",
            "password2",
        )

    def save(self, commit: bool = True) -> CustomUser:
        user = super().save(commit=False)
        user.role = "user"
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
    - available pickup: single location (we map to the M2M as the first/only value)
    - available return: multiple locations
    """

    car_type = forms.ChoiceField(choices=VehicleType.choices, label="Car Type")
    engine_type = forms.ChoiceField(choices=EngineType.choices, label="Engine Type")

    available_pickup_locations = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label="Pick-up Location",
        widget=forms.Select,
    )

    available_return_locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label="Drop-off Locations",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Vehicle
        fields = [
            "name",
            "car_type",
            "engine_type",
            "seats",
            "price_per_day",
            "plate_number",
            "year_of_manufacturing",
            "top_speed_kmh",
            "mileage_km",
            "fuel_consumption_l_100km",
            "damages",
            "available_pickup_locations",
            "available_return_locations",
        ]
        widgets = {
            "available_return_locations": forms.CheckboxSelectMultiple,
            "damages": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        request = kwargs.pop("request", None)
        instance: Vehicle | None = kwargs.get("instance")
        super().__init__(*args, **kwargs)

        self.fields["available_pickup_locations"].queryset = (
            Location.objects.all().order_by("name")
        )
        self.fields["available_return_locations"].queryset = (
            Location.objects.all().order_by("name")
        )

        if instance and instance.pk:
            first_pickup = instance.available_pickup_locations.first()
            if first_pickup:
                self.fields["available_pickup_locations"].initial = first_pickup.pk
            self.fields["available_return_locations"].initial = list(
                instance.available_return_locations.values_list("pk", flat=True)
            )
        elif not self.is_bound:
            default_id = None
            if request is not None:
                default_id = request.GET.get("pickup") or request.session.get(
                    "last_pickup_id"
                )
            fld = self.fields["available_pickup_locations"]
            if default_id and fld.queryset.filter(pk=default_id).exists():
                self.initial.setdefault("available_pickup_locations", int(default_id))

    def save(self, commit: bool = True) -> Vehicle:
        """
        Save the instance without Django's default M2M handling,
        then set M2M fields manually:
          - available_pickup_locations: single -> [single] (or empty)
          - available_return_locations: normal multiple
        """
        vehicle = super().save(commit=False)
        if commit:
            vehicle.save()

        pickup = self.cleaned_data.get("available_pickup_locations")
        returns = self.cleaned_data.get("available_return_locations")

        def _save_m2m() -> None:
            vehicle.available_pickup_locations.set([pickup] if pickup else [])
            vehicle.available_return_locations.set(returns if returns is not None else [])

        if commit:
            _save_m2m()
        else:
            self._save_m2m = _save_m2m  # type: ignore[attr-defined]

        return vehicle


class ReservationStatusForm(forms.ModelForm):
    class Meta:
        model = ReservationGroup
        fields = ["status"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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
    new_password = forms.CharField(
        widget=forms.PasswordInput(), min_length=8, label="New password"
    )
    new_password_confirm = forms.CharField(
        widget=forms.PasswordInput(), min_length=8, label="Confirm new password"
    )

    def clean(self) -> dict:
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("new_password_confirm"):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned


class VehicleFilterForm(forms.Form):
    """
    GET-based filter form for the vehicle list.
    """

    name = forms.CharField(
        required=False,
        label="Name",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Corolla"}),
    )
    plate = forms.CharField(
        required=False,
        label="Plate number",
        widget=forms.TextInput(attrs={"placeholder": "e.g. ABC-123"}),
    )
    car_type = forms.ChoiceField(
        required=False,
        label="Type of vehicle",
        choices=[("", "Any type")] + list(VehicleType.choices),
        widget=forms.Select(),
    )
    pickup_location = forms.ModelChoiceField(
        queryset=Location.objects.all().order_by("name"),
        required=False,
        empty_label="Any pickup location",
        label="Pickup location",
        widget=forms.Select(),
    )
    return_location = forms.ModelChoiceField(
        queryset=Location.objects.all().order_by("name"),
        required=False,
        empty_label="Any drop-off location",
        label="Drop-off location",
        widget=forms.Select(),
    )
