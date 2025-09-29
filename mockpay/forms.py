from __future__ import annotations

from dataclasses import dataclass

from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone
from django.db.models import TextChoices


@dataclass(frozen=True)
class CardConstraints:
    """Centralized constants for card validation."""

    min_pan_len: int = 13
    max_pan_len: int = 19
    min_cvc_len: int = 3
    max_cvc_len: int = 4
    min_year: int = 2000
    max_year: int = 2099


class Outcome(TextChoices):
    AUTO = "auto", "Auto"
    FORCE_SUCCESS = "success", "Force success"
    FORCE_FAIL = "fail", "Force fail"


def digits_only(text: str) -> str:
    """
    Return only the decimal digit characters from `text`.
    Keeps behavior explicit and predictable for inputs with spaces/dashes.
    """
    return "".join(ch for ch in text if ch.isdigit())


def luhn_is_valid(card_number_digits: str) -> bool:
    """
    Validate a string of digits using the Luhn checksum algorithm.
    Returns False if any non-digit sneaks in.
    """
    if not card_number_digits or not card_number_digits.isdigit():
        return False

    total = 0
    double = False
    for ch in reversed(card_number_digits):
        d = int(ch)
        if double:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        double = not double
    return (total % 10) == 0


class CheckoutForm(forms.Form):
    """
    Simple checkout/authorization form with conservative client-side style
    validations replicated on the server for safety.
    """

    card_number = forms.CharField(
        max_length=CardConstraints.max_pan_len,
        help_text="13–19 digits (spaces/dashes allowed).",
    )
    exp_month = forms.CharField(
        max_length=2,
        help_text="Two digits (MM).",
    )
    exp_year = forms.CharField(
        max_length=4,
        help_text="Four digits (YYYY).",
    )

    cvc = forms.CharField(
        max_length=CardConstraints.max_cvc_len,
        help_text="3 or 4 digits.",
    )

    cardholder_name = forms.CharField(
        max_length=96,
        required=False,
        help_text="Optional. Letters, spaces, and punctuation only.",
    )

    billing_country = forms.CharField(
        max_length=2,
        required=False,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z]{2}$", message="Use a 2-letter country code."
            )
        ],
        help_text="Optional. ISO 3166-1 alpha-2 (e.g., US, GB, DE).",
    )

    billing_postal = forms.CharField(
        max_length=12,
        required=False,
        help_text="Optional. Format varies by country.",
    )

    outcome = forms.ChoiceField(choices=Outcome.choices)

    def clean_card_number(self) -> str:
        raw = (self.cleaned_data.get("card_number") or "").strip()
        digits = digits_only(raw)

        if not (
            CardConstraints.min_pan_len <= len(digits) <= CardConstraints.max_pan_len
        ):
            raise forms.ValidationError("Card number must be 13–19 digits.")

        if not luhn_is_valid(digits):
            raise forms.ValidationError("Enter a valid card number.")

        # Normalize to digits only for downstream use/storage
        return digits

    def clean_cvc(self) -> str:
        raw = (self.cleaned_data.get("cvc") or "").strip()
        digits = digits_only(raw)
        if not (
            CardConstraints.min_cvc_len <= len(digits) <= CardConstraints.max_cvc_len
        ):
            raise forms.ValidationError("CVC must be 3 or 4 digits.")
        return digits

    def clean_exp_month(self) -> str:
        raw = (self.cleaned_data.get("exp_month") or "").strip()
        if not (len(raw) == 2 and raw.isdigit()):
            raise forms.ValidationError("Use MM for month (e.g., 02).")

        month = int(raw)
        if not (1 <= month <= 12):
            raise forms.ValidationError("Invalid expiry month.")
        # Keep the normalized two digit string (e.g., '02')
        return f"{month:02d}"

    def clean_exp_year(self) -> int:
        raw = (self.cleaned_data.get("exp_year") or "").strip()
        if not (len(raw) == 4 and raw.isdigit()):
            raise forms.ValidationError("Enter a valid 4-digit year (YYYY).")

        year = int(raw)
        if year < CardConstraints.min_year:
            raise forms.ValidationError(
                f"Year must be {CardConstraints.min_year} or later."
            )
        if year > CardConstraints.max_year:
            raise forms.ValidationError(
                f"Enter a realistic year (≤ {CardConstraints.max_year})."
            )

        return year

    def clean_cardholder_name(self) -> str:
        name = (self.cleaned_data.get("cardholder_name") or "").strip()

        if not name:
            return name

        if any(ch.isdigit() for ch in name):
            raise forms.ValidationError("Cardholder name cannot contain digits.")
        if len(name) < 2:
            raise forms.ValidationError("Enter the cardholder name.")
        return name

    def clean_billing_country(self) -> str:
        value = (self.cleaned_data.get("billing_country") or "").strip().upper()
        return value

    def clean_billing_postal(self) -> str:
        return (self.cleaned_data.get("billing_postal") or "").strip()

    def clean(self) -> dict:
        """
        Cross-field validation to ensure the expiry date is not in the past.
        Treats cards as valid through the last day of the expiry month.
        """
        cleaned = super().clean()

        exp_month = cleaned.get("exp_month")
        exp_year = cleaned.get("exp_year")

        if isinstance(exp_month, str) and isinstance(exp_year, int):
            try:
                month = int(exp_month)
                year = exp_year

                now = timezone.now()
                next_month_year = year + (1 if month == 12 else 0)
                next_month = 1 if month == 12 else (month + 1)

                first_of_next = timezone.datetime(
                    year=next_month_year,
                    month=next_month,
                    day=1,
                    tzinfo=now.tzinfo,
                )
                if now >= first_of_next:
                    raise forms.ValidationError("The card is expired.")
            except ValueError:
                pass

        return cleaned
