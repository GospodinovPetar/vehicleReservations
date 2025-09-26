from django import forms
from inventory.models.reservation import VehicleReservation


class ReservationEditForm(forms.ModelForm):
    class Meta:
        model = VehicleReservation
        fields = [
            "vehicle",
            "pickup_location",
            "return_location",
            "start_date",
            "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
