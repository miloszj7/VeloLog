"""Named values for the trip form's validation boundaries."""

from datetime import timedelta

# Slack allowed on `TripForm.clean_date`'s "not in the future" rule. One day, and the
# reason is exact rather than defensive: `TIME_ZONE = "UTC"` with `USE_TZ = True`
# (`velo_log/settings.py`) makes `timezone.localdate()` the *UTC* date, while the
# `type="date"` widget submits the rider's *local* date. A rider at UTC+2 logging a ride at
# local 01:00 is posting tomorrow's UTC date, and would be refused by a bare
# `value > localdate()`. No real timezone runs more than 14 hours ahead of UTC, so a local
# date can never exceed the UTC date by more than one — one day closes that window exactly,
# and nothing wider is needed to close it.
FUTURE_TRIP_DATE_TOLERANCE = timedelta(days=1)

# Slack allowed between the rider-entered `Trip.date` and a GPX-observed timestamp
# (`gpx.stages.trip_span`'s start, an uploaded stage's `started_at`, or the trip list's
# per-trip earliest stage) before the two count as diverging. One day for the same reason
# as above — it absorbs the UTC-storage-vs-local-input slack — and must not flag
# `tests/gpx/fixtures/timed-track-day-2.gpx` (exactly one day after the `trip` fixture's
# date) as diverging from it.
TRIP_DATE_DIVERGENCE_TOLERANCE = timedelta(days=1)
