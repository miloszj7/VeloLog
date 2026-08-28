"""Recomputes a stored track's statistics from the file it was parsed out of.

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
"""

import logging

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
