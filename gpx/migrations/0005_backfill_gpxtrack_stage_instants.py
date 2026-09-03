"""Fills the stage instants `0004` added, for the rows that predate them.

Separate from `0004` on purpose, per the additive-first migration rule the `0002`/`0003`
pair established: the schema change and the data write are independently reversible, and
reversing this one is a no-op.

Without this pass, a trip that *already* had a stage can never establish chronology when a
second one joins it — `gpx.stages.chronology_is_established` requires every stage to carry
a `started_at`, so the page would say "upload order" and draw no stage breaks however many
timed stages were added afterwards. `manage.py backfill_gpx_stats --all` refills the same
columns, and is the recovery path when this migration runs against a misconfigured
`MEDIA_ROOT` and reads nothing: a migration cannot be re-applied once recorded.
"""

import logging

from django.db import migrations, transaction
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

logger = logging.getLogger(__name__)

# The columns a backfill writes as they exist at *this* migration's schema state — the
# four `0002` added plus the two `0004` did. Pinned rather than imported from
# `gpx.statistics`, whose `STATS_FIELDS` tracks the current model and grows: the two
# instants joined it only after `0004`, and `0003` was already narrowing a historical
# queryset with that live tuple when they did. `.only()` raised `FieldDoesNotExist` from
# `pending.iterator()` — outside the per-row guard — failing the unattended `migrate` at
# container boot on every fresh database. A migration's field list is history, not
# configuration, so this one carries its own even though today it happens to match.
STATS_COLUMNS_AT_0004 = (
    "distance_meters",
    "duration_seconds",
    "elevation_gain_meters",
    "elevation_loss_meters",
    "started_at",
    "ended_at",
)


def backfill_stage_instants(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Refill every row whose stage instants are still null, best effort.

    The import sits *inside* this function for the reason `0003` spells out in full: a
    module-level import is evaluated when Django builds the migration graph, so a later
    rename of `gpx.statistics` would break `migrate`, `makemigrations --check` and
    `manage.py check` at once, before the per-row guard could absorb anything. Under the
    guard the same rename degrades to one logged skip, and a replay on a fresh database
    still succeeds. `except Exception` rather than `except ImportError` for the same
    reason too — a `SyntaxError`, a `NameError` or a new circular import inside that
    module is the same event from here.
    """
    try:
        from gpx.statistics import backfill_track_statistics
    except Exception:
        logger.exception(
            "gpx.statistics is unavailable; leaving existing stage instants null. "
            "Run `manage.py backfill_gpx_stats --all` once it is importable again."
        )
        return

    gpx_track = apps.get_model("gpx", "GpxTrack")
    tracks = gpx_track.objects.using(schema_editor.connection.alias)
    # `started_at__isnull=True` is sound *here* and wrong for the management command, and
    # the difference is that a migration runs exactly once. The worst case is that every
    # untimed row is re-parsed one time for nothing. It is not a convergence predicate:
    # the both-or-neither rule at the parse boundary makes null permanent for a file with
    # no usable `<time>`, so a command filtering on it would re-select the same rows for
    # ever and its pending tally could never reach zero. `0003` had `distance_meters`,
    # the one statistic never legitimately null once computed; there is no instant column
    # with that property, which is why the command keeps `0003`'s filter and offers
    # `--all` instead.
    #
    # `.only(...)` keeps the `points` blob — up to `MAX_GPX_POINTS` coordinate pairs, tens
    # of megabytes once hydrated — off a loop that runs unattended at container boot on a
    # memory-capped dyno and reads none of it. `save(update_fields=...)` is happy on a
    # deferred instance, and `.iterator()` keeps the result set itself from being
    # materialized in one go.
    pending = tracks.filter(started_at__isnull=True).only("id", "file", *STATS_COLUMNS_AT_0004)
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
            # parse. What is left is the `save()` — and this runs unattended at container
            # boot, where one bad row must not stop the deploy. Those columns stay null,
            # the stage list says the order is upload order rather than claiming a
            # chronology it cannot evidence, and `manage.py backfill_gpx_stats --all` is
            # the recovery path.
            logger.exception("Could not backfill stage instants", extra={"track_id": track.pk})


class Migration(migrations.Migration):

    dependencies = [
        ("gpx", "0004_gpxtrack_stage_instants"),
    ]

    operations = [
        # `noop` reverse rather than a nulling pass, as in `0003`: reversing past this
        # migration reaches `0004`, which drops both columns outright, so undoing the data
        # write on the way there would be work with nothing to show for it.
        migrations.RunPython(backfill_stage_instants, migrations.RunPython.noop),
    ]
