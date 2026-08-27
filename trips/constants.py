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
