from __future__ import annotations

from django import forms
from django.utils import timezone


OUTCOME_CHOICES = [
    ("auto", "Auto"),
    ("success", "Force success"),
    ("fail", "Force fail"),
]


def digits_only(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def luhn_is_valid(card_number_digits: str) -> bool:
    total = 0
    should_double = False
    for ch in reversed(card_number_digits):
        if not ch.isdigit():
            return False
        digit = ord(ch) - 48
        if should_double:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
        should_double = not should_double
    return (total % 10) == 0


class CheckoutForm(forms.Form):
    card_number = forms.CharField(max_length=19)
    exp_month = forms.CharField(max_length=2)
    exp_year = forms.CharField(max_length=4)
    cvc = forms.CharField(max_length=4)
    cardholder_name = forms.CharField(max_length=96, required=False)
    billing_country = forms.CharField(max_length=2, required=False)
    billing_postal = forms.CharField(max_length=12, required=False)
    outcome = forms.ChoiceField(choices=OUTCOME_CHOICES)

    def clean_card_number(self) -> str:
        raw = self.cleaned_data.get("card_number", "")
        digits = digits_only(raw)
        if not (13 <= len(digits) <= 19):
            raise forms.ValidationError("Card number must be 13–19 digits.")
        if not luhn_is_valid(digits):
            raise forms.ValidationError("Enter a valid card number.")
        return digits

    def clean_cvc(self) -> str:
        raw = self.cleaned_data.get("cvc", "")
        digits = digits_only(raw)
        if not (3 <= len(digits) <= 4):
            raise forms.ValidationError("CVC must be 3 or 4 digits.")
        return digits

    def clean_exp_month(self) -> str:
        mm = self.cleaned_data.get("exp_month", "")
        if not (len(mm) == 2 and mm.isdigit()):
            raise forms.ValidationError("Use MM for month.")
        month = int(mm)
        if month < 1 or month > 12:
            raise forms.ValidationError("Invalid expiry month.")
        return mm

    def clean_exp_year(self) -> str:
        yy = self.cleaned_data.get("exp_year", "")
        if not (len(yy) in (2, 4) and yy.isdigit()):
            raise forms.ValidationError("Use YY or YYYY for year.")
        if len(yy) == 2:
            yy_full = 2000 + int(yy)
        else:
            yy_full = int(yy)
        now = timezone.now()
        mm = self.cleaned_data.get("exp_month")
        month = int(mm) if mm and mm.isdigit() else 1
        if yy_full < now.year or (yy_full == now.year and month < now.month):
            raise forms.ValidationError("Card is expired.")
        return str(yy_full)

    def clean_cardholder_name(self) -> str:
        name = (self.cleaned_data.get("cardholder_name") or "").strip()
        if name and len(name) < 2:
            raise forms.ValidationError("Enter the cardholder name.")
        return name

    def clean_billing_country(self) -> str:
        value = (self.cleaned_data.get("billing_country") or "").strip().upper()
        if value and len(value) != 2:
            raise forms.ValidationError("Use 2-letter country code.")
        return value

    def clean_billing_postal(self) -> str:
        value = (self.cleaned_data.get("billing_postal") or "").strip()
        return value
