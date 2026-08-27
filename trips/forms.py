from datetime import date
from typing import TYPE_CHECKING

from django import forms
from django.utils import timezone

from trips.constants import FUTURE_TRIP_DATE_TOLERANCE
from trips.models import Trip

if TYPE_CHECKING:
    _TripFormBase = forms.ModelForm[Trip]
else:
    _TripFormBase = forms.ModelForm


class TripForm(_TripFormBase):
    """Collects a trip's name, date, and description. Owner is set server-side."""

    class Meta:
        model = Trip
        fields = ("name", "date", "description")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }
        # `help_texts`, **plural**. `ModelFormOptions` reads
        # `getattr(options, "help_texts", None)`, so a singular `help_text = {...}` here is
        # silently ignored — no error, nothing rendered, every gate green. That is why
        # `tests/trips/test_trip_creation.py` asserts this sentence in the *rendered* page
        # rather than trusting the key: a typo is otherwise invisible.
        #
        # `labels` is deliberately not used. The auto-derived label is already "Date"; what
        # was missing is the sentence saying *which* date, which is what the future-date
        # rule below now enforces.
        help_texts = {
            "date": "The day the ride happened — VeloLog is a diary, not a planner.",
        }

    def clean_date(self) -> date:
        """Reject a date too far ahead to be a ride that already happened.

        Skipped when the date is unchanged, and that guard is the half that prevents a trap
        rather than adding a rule: a trip already stored with a future date — created
        through the admin, which keeps a plain `ModelForm`, or before this rule existed —
        must stay editable. Without the guard a rider could not fix such a trip's name
        without also moving its date, and this is the very slice that introduces editing.
        """
        value: date = self.cleaned_data["date"]
        if "date" not in self.changed_data:
            return value
        if value > timezone.localdate() + FUTURE_TRIP_DATE_TOLERANCE:
            raise forms.ValidationError(
                "A trip cannot be dated in the future. Log a ride once you have ridden it."
            )
        return value
