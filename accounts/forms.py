from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from inventory.models.reservation import (
    ReservationStatus,
    Location,
    ReservationGroup,
)
from inventory.models.vehicle import Vehicle, VehicleType, EngineType

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
    - available pickup: single location (we map to the M2M as the first/only value)
    - available return: multiple locations
    """

    car_type = forms.ChoiceField(choices=VehicleType.choices, label="Car Type")
    engine_type = forms.ChoiceField(choices=EngineType.choices, label="Engine Type")

    # Single selection for pick-up (mapped to M2M in save())
    available_pickup_locations = forms.ModelChoiceField(
        queryset=Location.objects.none(),  # set properly in __init__
        required=True,
        label="Pick-up Location",
        widget=forms.Select,
    )

    # Multiple selection for drop-off
    available_return_locations = forms.ModelMultipleChoiceField(
        queryset=Location.objects.none(),  # set properly in __init__
        required=True,
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
            "available_pickup_locations",
            "available_return_locations",
            "plate_number",
        ]
        widgets = {
            "available_return_locations": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        instance: Vehicle | None = kwargs.get("instance")

        super().__init__(*args, **kwargs)

        self.fields["available_pickup_locations"].queryset = (
            Location.objects.all().order_by("name")
        )
        self.fields["available_return_locations"].queryset = (
            Location.objects.all().order_by("name")
        )

        self.fields["available_pickup_locations"].empty_label = None

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
            else:
                first = fld.queryset.first()
                if first:
                    self.initial.setdefault("available_pickup_locations", first.pk)

    def save(self, commit=True):
        """
        Save the instance without Django's default M2M handling,
        then set M2M fields manually:
          - available_pickup_locations: single -> [single]
          - available_return_locations: normal multiple
        """
        # 1) Avoid default _save_m2m by using commit=False
        vehicle = super().save(commit=False)

        # 2) Save the instance so M2Ms can be set
        if commit:
            vehicle.save()

        # 3) Grab cleaned data
        pickup = self.cleaned_data.get("available_pickup_locations")
        returns = self.cleaned_data.get("available_return_locations")

        def _save_m2m():
            vehicle.available_pickup_locations.set([pickup] if pickup else [])
            # multiple is already an iterable
            vehicle.available_return_locations.set(
                returns if returns is not None else []
            )

        # 5) Execute now or defer (Django pattern when commit=False)
        if commit:
            _save_m2m()
        else:
            self._save_m2m = _save_m2m  # caller can run this later

        return vehicle


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
    new_password = forms.CharField(
        widget=forms.PasswordInput(), min_length=8, label="New password"
    )
    new_password_confirm = forms.CharField(
        widget=forms.PasswordInput(), min_length=8, label="Confirm new password"
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("new_password_confirm"):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned
