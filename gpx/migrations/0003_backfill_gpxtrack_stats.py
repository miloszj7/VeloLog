"""Fills the statistics columns `0002` added, for the rows that predate them.

Separate from `0002` on purpose, per the additive-first migration rule: the schema change
and the data write are independently reversible, and reversing this one is a no-op.
"""

import logging

from django.db import migrations, transaction
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

logger = logging.getLogger(__name__)


def backfill_stats(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Refill every row whose statistics are still null, best effort.

    The import sits *inside* this function rather than at module level, and that
    placement is load-bearing. A module-level `from gpx.statistics import …` is evaluated
    when Django builds the migration graph — before a single row is touched — so a later
    rename or move of that module would break `migrate`, `makemigrations --check` and
    `manage.py check` all at once, and the per-row guard below would never get the chance
    to run. Under the guard the same rename degrades to one logged skip, and a replay on
    a fresh database still succeeds.

    The guard is `except Exception`, not `except ImportError`. A rename or a move raises
    `ModuleNotFoundError` and would be caught either way, but a module-level `SyntaxError`,
    a `NameError` or a new circular import inside `gpx.statistics` is the same event from
    this migration's point of view — application code changed shape — and produces exactly
    the triple break described above. `ImportError` alone would let all three through.
    """
    try:
        from gpx.statistics import STATS_FIELDS, backfill_track_statistics
    except Exception:
        logger.exception(
            "gpx.statistics is unavailable; leaving existing track statistics null. "
            "Run `manage.py backfill_gpx_stats` once it is importable again."
        )
        return

    gpx_track = apps.get_model("gpx", "GpxTrack")
    # `distance_meters` is the null probe because it is the one statistic that is never
    # null once computed: `length_2d()` always returns a float, and an empty track is
    # rejected at upload. The other three are legitimately null for a file that carried
    # no `<ele>` or no `<time>`, so filtering on any of them would refill rows forever.
    tracks = gpx_track.objects.using(schema_editor.connection.alias)
    # `.only(...)` matters here more than anywhere else this queryset shape appears: this
    # loop runs unattended at container boot on a memory-capped dyno, and a whole row
    # carries the `points` blob — up to `MAX_GPX_POINTS` coordinate pairs, tens of
    # megabytes once hydrated into Python lists — which nothing below reads.
    # `save(update_fields=...)` is happy on a deferred instance, so this costs nothing, and
    # `.iterator()` keeps the result set itself from being materialized in one go.
    pending = tracks.filter(distance_meters__isnull=True).only("id", "file", *STATS_FIELDS)
    for track in pending.iterator():
        try:
            # The inner `atomic()` is a savepoint, and it is what makes the broad catch
            # below mean what its comment says. `Model.save_base` wraps its write in
            # `mark_for_rollback_on_error`, which sets `needs_rollback` on the enclosing
            # transaction *before* re-raising — so without a savepoint to unwind, catching
            # the error here leaves the transaction poisoned: every later row's `save()`
            # raises `TransactionManagementError`, this same catch swallows that too, and
            # `Atomic.__exit__` rolls the whole migration back without raising. `migrate`
            # would print OK and exit 0 having written nothing.
            with transaction.atomic():
                backfill_track_statistics(track)
        except Exception:
            # The helper already absorbs an unreadable file and bytes that no longer
            # parse. What is left is the `save()` and whatever a future version of the
            # helper adds — and this runs unattended at container boot, where one bad row
            # must not stop the deploy. Those columns stay null, the detail page says so
            # in words, and `manage.py backfill_gpx_stats` is the recovery path.
            logger.exception("Could not backfill track statistics", extra={"track_id": track.pk})


class Migration(migrations.Migration):

    dependencies = [
        ("gpx", "0002_gpxtrack_stats"),
    ]

    operations = [
        # `noop` reverse rather than a nulling pass: reversing past this migration reaches
        # `0002`, which drops the four columns outright, so undoing the data write on the
        # way there would be work with nothing to show for it.
        migrations.RunPython(backfill_stats, migrations.RunPython.noop),
    ]
