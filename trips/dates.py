"""Comparison logic shared by every surface that flags Trip.date vs GPX divergence."""

from datetime import date, datetime, timedelta

from django.utils import timezone

from trips.constants import TRIP_DATE_DIVERGENCE_TOLERANCE


def trip_date_diverges(
    trip_date: date,
    observed: datetime,
    tolerance: timedelta = TRIP_DATE_DIVERGENCE_TOLERANCE,
) -> bool:
    """Decide whether an observed GPX timestamp diverges from the logged Trip.date.

    `observed` is converted via `timezone.localtime(observed).date()` before comparing —
    the same conversion `trip_detail.html`'s `|date` filter already performs on datetimes —
    so this agrees with what the template would show if it rendered both dates directly.
    Strictly greater than `tolerance`, matching `TripForm.clean_date`'s boundary convention:
    a difference exactly equal to the tolerance does not diverge.
    """
    observed_date = timezone.localtime(observed).date()
    return abs(observed_date - trip_date) > tolerance
