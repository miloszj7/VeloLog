from typing import TYPE_CHECKING

from django import forms

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
