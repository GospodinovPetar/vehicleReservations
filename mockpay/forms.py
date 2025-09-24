# mockpay/forms.py
from __future__ import annotations
from django import forms
from django.utils import timezone

OUTCOME_CHOICES = [
    ("auto", "Auto (based on card)"),
    ("success", "Force success"),
    ("fail", "Force failure"),
    ("cancel", "Force cancel"),
    ("challenge", "Force 3-D Secure challenge"),
]

def digits_only(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())

def luhn_is_valid(card_number_digits: str) -> bool:
    total, should_double = 0, False
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
    # Card fields
    card_number = forms.CharField(
        label="Card number",
        max_length=19,
        help_text="Enter digits or spaced groups (e.g. 4242 4242 4242 4242).",
        widget=forms.TextInput(attrs={
            "autocomplete": "cc-number",
            "inputmode": "numeric",
            "placeholder": "1234 1234 1234 1234",
            "pattern": r"[0-9 ]*",
            "class": "input",
        }),
    )
    card_expiry = forms.CharField(
        label="Expiry (MM/YY)",
        max_length=5,
        widget=forms.TextInput(attrs={
            "autocomplete": "cc-exp",
            "placeholder": "MM/YY",
            "class": "input",
        }),
    )
    card_cvc = forms.CharField(
        label="CVC",
        max_length=4,
        help_text="3 or 4 digits.",
        widget=forms.TextInput(attrs={
            "autocomplete": "cc-csc",
            "inputmode": "numeric",
            "placeholder": "CVC",
            "class": "input",
        }),
    )
    cardholder_name = forms.CharField(
        label="Name on card",
        max_length=64,
        widget=forms.TextInput(attrs={
            "autocomplete": "cc-name",
            "placeholder": "Jane Doe",
            "class": "input",
        }),
    )

    # Billing fields
    billing_country = forms.ChoiceField(
        label="Country",
        choices=[("", "Select…"), ("BG", "Bulgaria"), ("DE", "Germany"),
                 ("FR", "France"), ("US", "United States")],
        widget=forms.Select(attrs={"class": "input"}),
    )

    # Mock control
    outcome = forms.ChoiceField(
        label="Simulate outcome",
        choices=OUTCOME_CHOICES,
        initial="auto",
        widget=forms.Select(attrs={"class": "input"}),
    )

    # ---- Validation ----
    def clean_card_number(self) -> str:
        raw = self.cleaned_data["card_number"]
        digits = digits_only(raw)
        if not (13 <= len(digits) <= 19):
            raise forms.ValidationError("Card number must be 13–19 digits.")
        if not luhn_is_valid(digits):
            raise forms.ValidationError("Enter a valid card number.")
        return digits

    def clean_card_cvc(self) -> str:
        raw = self.cleaned_data["card_cvc"]
        digits = digits_only(raw)
        if not (3 <= len(digits) <= 4):
            raise forms.ValidationError("CVC must be 3 or 4 digits.")
        return digits

    def clean_card_expiry(self) -> str:
        value = self.cleaned_data["card_expiry"]
        if len(value) != 5 or value[2] != "/":
            raise forms.ValidationError("Use the format MM/YY.")
        mm_str, yy_str = value[:2], value[3:]
        if not (mm_str.isdigit() and yy_str.isdigit()):
            raise forms.ValidationError("Use the format MM/YY.")
        month = int(mm_str)
        year = int("20" + yy_str)
        if month < 1 or month > 12:
            raise forms.ValidationError("Invalid expiry month.")
        now = timezone.now()
        if year < now.year or (year == now.year and month < now.month):
            raise forms.ValidationError("Card is expired.")
        return value

    def clean_cardholder_name(self) -> str:
        name = (self.cleaned_data.get("cardholder_name") or "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Enter the cardholder name.")
        return name

    def clean_billing_country(self) -> str:
        country = self.cleaned_data["billing_country"]
        if not country:
            raise forms.ValidationError("Please select a country.")
        return country
