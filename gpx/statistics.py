"""The two ends of the four statistics columns: refilling them, and shaping them for display.

One module rather than two because both halves are defined by the same column set, and the
zero-versus-null distinction those columns exist to preserve has to be honoured identically
at both ends. `STATS_FIELDS` below names the set once; `build_trip_stats` reads exactly it.

Refilling
---------

The four statistics columns on `GpxTrack` are filled at upload by
`GpxUploadForm.clean_file`, which has the parse result already in hand. Rows uploaded
before those columns existed never had that moment, so they are refilled here — from the
bytes still in storage, through the same `gpx.parsing` boundary the upload path uses, so
a backfilled row and a freshly uploaded one cannot disagree about the same file.

This is application code rather than logic living inside the migration that needs it, for
one reason: migrations run against an empty in-memory database under `pytest`, so a data
migration proves nothing about itself. The helper below is unit-tested directly.

**Pinned by `gpx/migrations/0003_backfill_gpxtrack_stats.py`**, which imports it inside
its `RunPython` body, and by `manage.py backfill_gpx_stats`. It cannot be deleted while
that migration exists: a replay on a fresh database would degrade to one logged skip and
leave every pre-existing row's statistics null. Renaming it is survivable — the
migration's import sits under a guard, deliberately — but silent, which is worse than a
break.

Displaying
----------

`build_trip_stats` shares `gpx/map_config.py`'s `build_map_config` "or `None` when there is
nothing to show" discipline — the template is handed a finished blob or `None`, and does no
arithmetic of its own — but not its input type: `build_map_config` takes `Sequence[Stage]`
(one call, all stages) while `build_trip_stats` deliberately keeps its single-track
signature, called once per stage by `gpx.stages.build_stages`. Both live outside the two
views for the same reason: two views render `trips/trip_detail.html`, and a value derived
in a template would have to be derived twice.
"""

import logging
import math
from dataclasses import dataclass

from gpx.constants import METERS_PER_KILOMETER, SECONDS_PER_HOUR, SECONDS_PER_MINUTE
from gpx.models import GpxTrack
from gpx.parsing import parse_gpx_bytes

logger = logging.getLogger(__name__)

STATS_FIELDS = (
    "distance_meters",
    "duration_seconds",
    "elevation_gain_meters",
    "elevation_loss_meters",
)
"""The only columns a backfill ever writes.

Named once so the helper's `update_fields`, the migration's null-row filter and the
management command's cannot drift apart — and so it stays visible that `points` and the
four bounds are not in the list. Those are what the map draws, they are already correct,
and a backfill has no business rewriting them.
"""


def backfill_track_statistics(track: GpxTrack) -> bool:
    """Recompute one track's statistics from its stored file and save only those columns.

    Args:
        track: The row to refill. May be the historical model instance a data migration
            passes rather than a real `GpxTrack` — nothing here touches anything but
            `file` and the four statistics columns, all of which exist in every version
            of the schema that has the columns at all.

    Returns:
        Whether the row was refilled. `False` means the file could not be read or no
        longer parses, and the row's columns are left exactly as they were — for a
        pre-existing row that means still null, which the detail page renders as an
        explicit sentence rather than as four zeroes.
    """
    try:
        with track.file.open("rb") as stored:
            raw = stored.read()
        parsed = parse_gpx_bytes(raw)
    except Exception:
        # Broad on purpose, for the same reason `gpx/signals.py`'s cleanup is: every
        # failure reachable here is operational, and no caller can act on which one it
        # was. A missing file raises `FileNotFoundError`, a row with no file name raises
        # `ValueError`, a key that no longer resolves raises `SuspiciousFileOperation`
        # (a `ValueError` too), a remote backend raises its own client error, and bytes
        # that no longer parse raise `GpxParseError` — five unrelated types, none of
        # which a best-effort refill may let escape into the unattended `migrate` that
        # runs at container boot. `logger.exception` is what stops a programming error in
        # here from vanishing along with them.
        logger.exception(
            "Could not recompute track statistics",
            extra={"track_id": track.pk, "storage_key": track.file.name},
        )
        return False

    track.distance_meters = parsed.distance_meters
    track.duration_seconds = parsed.duration_seconds
    track.elevation_gain_meters = parsed.elevation_gain_meters
    track.elevation_loss_meters = parsed.elevation_loss_meters
    # `update_fields` naming only the statistics is the whole safety property of the
    # backfill: a bare `save()` would rewrite `points` and the bounds from this in-memory
    # instance, so a bug anywhere upstream of here could damage the route on a row that
    # was rendering perfectly well.
    track.save(update_fields=list(STATS_FIELDS))
    return True


def _round_half_up(value: float) -> int:
    """Round to the nearest integer, sending an exact half away from zero.

    Args:
        value: The figure to round. Never negative here — a distance, a count of minutes
            and a total climb are all magnitudes — so "away from zero" and "up" coincide.

    Returns:
        The rounded integer. Python's built-in `round` is round-half-to-even, which makes
        the half boundary alternate direction; every display figure in this module wants
        one consistent rule instead.
    """
    return math.floor(value + 0.5)


def format_distance(meters: float | None) -> str | None:
    """Render a stored distance as kilometres to one decimal place, or `None` for `None`.

    Args:
        meters: The stored `distance_meters`, or `None` when the row has no value.

    Returns:
        A string such as `"36.6 km"`, or `None`. `0.0` metres formats as `"0.0 km"` — a
        real answer for a track whose points are all identical, and deliberately not the
        same outcome as an absent value.
    """
    if meters is None:
        return None
    return f"{meters / METERS_PER_KILOMETER:.1f} km"


def format_duration(seconds: float | None) -> str | None:
    """Render a stored recorded time as hours and minutes, or `None` for `None`.

    Args:
        seconds: The stored `duration_seconds`, or `None` when the file carried no usable
            timestamps — see `ParsedTrack`. This is the sum of each segment's own span,
            so a multi-day tour's
            overnight gaps are not in it — the template labels it "Recorded time" for that
            reason, and this function is not the place the semantic is explained twice.

    Returns:
        A string such as `"2 h 15 min"`, or `"45 min"` under an hour, or `None`. Minutes
        are zero-padded only in the two-part form, where the reading is a clock-like pair.
    """
    if seconds is None:
        return None
    # Rounded to whole minutes *before* the split, not after: rounding each part
    # separately turns 3599.9 seconds into "60 min" rather than into "1 h 00 min".
    #
    # `math.floor(x + 0.5)` rather than `round`, which is round-half-to-even: `round`
    # sends 30 seconds to "0 min" while sending 90 to "2 min", and "0 min" for a track
    # that recorded half a minute is one of the strings this slice exists to avoid.
    rounded_seconds = _round_half_up(seconds / SECONDS_PER_MINUTE) * SECONDS_PER_MINUTE
    hours, remainder = divmod(rounded_seconds, SECONDS_PER_HOUR)
    minutes = remainder // SECONDS_PER_MINUTE
    if not hours:
        return f"{minutes} min"
    return f"{hours} h {minutes:02d} min"


def format_elevation(meters: float | None) -> str | None:
    """Render a stored elevation change as whole metres, or `None` for `None`.

    Args:
        meters: The stored `elevation_gain_meters` or `elevation_loss_meters`, or `None`
            when the file carried no usable `<ele>` — see `ParsedTrack`.

    Returns:
        A string such as `"1240 m"`, or `None`. Whole metres because the underlying figure
        is a sum of noisy per-point deltas — a decimal place would advertise a precision
        the input does not have.
    """
    if meters is None:
        return None
    # Half-up for the same reason as `format_duration`: `round` is round-half-to-even, so
    # it sends 0.5 m to "0 m" and 1.5 m to "2 m" — an inconsistent boundary, and the low
    # side of it prints the "nothing here" figure for a real measurement.
    return f"{_round_half_up(meters)} m"


@dataclass(frozen=True)
class TripStats:
    """The four statistics as the detail template renders them, already formatted.

    Every field is `str | None`, and a `None` means one thing only: the stored column was
    null, so the uploaded file did not carry what that stat is derived from. The template
    turns each `None` into a sentence naming the file as the reason — never into a blank
    cell, and never into a zero.
    """

    distance: str | None
    recorded_time: str | None
    elevation_gain: str | None
    elevation_loss: str | None


def build_trip_stats(track: GpxTrack | None) -> TripStats | None:
    """Return the blob the detail template renders, or `None` if there are no stats to show.

    Args:
        track: The trip's current track, or `None` when nothing has been uploaded.

    Returns:
        Formatted statistics, or `None` when there is no track at all or when every stored
        column is null. The second case is a row that predates the columns and whose
        backfill never reached it; the template gives it its own sentence, because
        "nobody has computed these" and "the file did not carry this" are different
        failures and a bug report has to be able to tell them apart.

    The all-null test is `all(value is None ...)`, never a falsy check. A track whose
    points are all identical stores `distance_meters = 0.0` — legal, non-null and falsy —
    and a falsy check would collapse that perfectly parsed track into the re-upload
    sentence. Same zero-versus-null trap `gpx.parsing.track_statistics` guards at the parse
    boundary, one layer up.
    """
    if track is None:
        return None
    # Spelled out rather than `getattr` over `STATS_FIELDS`: a `getattr` loop types as
    # `list[Any]`, so `mypy --strict` would verify nothing about these four names matching
    # real fields and a typo in the tuple would surface as an `AttributeError` on every
    # detail page render. `STATS_FIELDS` still names the set for `update_fields` and the
    # backfill filters, where the values are column names rather than attribute reads.
    stored = (
        track.distance_meters,
        track.duration_seconds,
        track.elevation_gain_meters,
        track.elevation_loss_meters,
    )
    if all(value is None for value in stored):
        return None
    return TripStats(
        distance=format_distance(track.distance_meters),
        recorded_time=format_duration(track.duration_seconds),
        elevation_gain=format_elevation(track.elevation_gain_meters),
        elevation_loss=format_elevation(track.elevation_loss_meters),
    )
