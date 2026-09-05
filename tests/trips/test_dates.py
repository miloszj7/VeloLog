"""`trips.dates.trip_date_diverges` — the one comparison every divergence surface calls.

Cases: same day, exactly at the tolerance boundary (not diverging — matches
`TripForm.clean_date`'s strictly-greater-than convention), one day beyond it (diverging),
and a non-UTC `TIME_ZONE` override proving the function converts `observed` via
`timezone.localtime` before comparing dates, rather than reading its UTC date directly.
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone

from django.test import override_settings

from trips.dates import trip_date_diverges

TRIP_DATE = date(2026, 6, 1)


def test_same_day_does_not_diverge() -> None:
    observed = datetime(2026, 6, 1, 10, 0, tzinfo=dt_timezone.utc)
    assert trip_date_diverges(TRIP_DATE, observed) is False


def test_exactly_at_tolerance_boundary_does_not_diverge() -> None:
    """One day apart equals the tolerance — strictly-greater-than means this stays False."""
    observed = datetime(2026, 6, 2, 0, 0, tzinfo=dt_timezone.utc)
    assert trip_date_diverges(TRIP_DATE, observed) is False


def test_one_day_beyond_tolerance_diverges() -> None:
    observed = datetime(2026, 6, 3, 0, 0, tzinfo=dt_timezone.utc)
    assert trip_date_diverges(TRIP_DATE, observed) is True


def test_converts_via_localtime_before_comparing_dates() -> None:
    """Same UTC instant, two `TIME_ZONE` settings, two different verdicts.

    In UTC the observed instant's date is 2026-06-02 (one day out — at the boundary, not
    diverging). Shifted forward by the +14h `Pacific/Kiritimati` offset it rolls to
    2026-06-03 (two days out — diverging). If the function compared the bare UTC date
    instead of converting via `timezone.localtime`, the second assertion would fail.
    """
    observed = datetime(2026, 6, 2, 23, 0, tzinfo=dt_timezone.utc)

    assert trip_date_diverges(TRIP_DATE, observed) is False

    with override_settings(TIME_ZONE="Pacific/Kiritimati"):
        assert trip_date_diverges(TRIP_DATE, observed) is True
