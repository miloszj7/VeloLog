"""`manage.py backfill_gpx_stats` — the recovery path for a backfill that filled nothing.

Migrations `0003` (the four statistics) and `0005` (the two stage instants) each run once,
unattended, at container boot, and their most likely failure is a misconfigured
`MEDIA_ROOT` — the one operational fault this repo has escalated to a Hard Rule in
`AGENTS.md`, documented in `DEPLOY.md` and wired into `/healthz/`. If that deploy is the
deploy they apply on, they read no files, fill nothing, and can never be re-run: a
migration cannot be re-applied once recorded. This command is what makes that one
invocation to recover instead of re-uploading every file by hand — with `--all` for the
instants, since the default filter below cannot reach a row whose statistics already
landed.

It carries no computation of its own — every line of that lives in `gpx/statistics.py`,
the same helper the migration calls, so the two cannot drift.
"""

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from gpx.models import GpxTrack
from gpx.statistics import STATS_FIELDS, backfill_track_statistics

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Recompute the statistics columns and stage instants on stored GPX tracks "
        "from their files."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--all",
            action="store_true",
            help=(
                "Reprocess every track, not only those whose statistics are null — for a "
                "track whose file was replaced or whose stored figures are stale, and the "
                "only way to refill stage instants on a row whose statistics are already "
                "present."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Refill the selected tracks and report a tally, exiting 0 even on skips.

        A partially unreadable media directory is exactly the situation this command
        exists for, so it is a report rather than a crash: the helper absorbs a row whose
        file cannot be read, the loop below absorbs a row whose write fails, and the tally
        is what tells the operator how many rows are still waiting on a corrected
        `MEDIA_ROOT`.
        """
        tracks = GpxTrack.objects.all()
        if not options["all"]:
            # `0003`'s probe, for `0003`'s reason: `distance_meters` is the one column a
            # backfill writes that is never null once computed, so any other would select
            # rows whose file simply carried no `<ele>` or no `<time>` over and over
            # again. `0005` filters on `started_at` instead and is right to — it runs
            # exactly once, so re-parsing every untimed row one time for nothing is its
            # whole cost. Here it would be permanent: an untimed row would be pending on
            # every invocation and the tally could never reach zero, which is this
            # command's only signal that there is nothing left to do. `--all` is the path
            # that refills instants, and it converges by being finite.
            tracks = tracks.filter(distance_meters__isnull=True)

        # Deferred for the same reason as in migration `0003`: the `points` blob is the
        # largest thing on the row and no part of this command reads it. `original_filename`
        # is in the list because the skip line below prints it — leaving it deferred would
        # trade one big column for a refresh query per skipped row.
        tracks = tracks.only("id", "file", "original_filename", *STATS_FIELDS)

        filled = 0
        skipped = 0
        for track in tracks.iterator():
            try:
                refilled = backfill_track_statistics(track)
            except Exception:
                # The helper absorbs an unreadable file and bytes that no longer parse on
                # its own, so what reaches here is the `save()`. A tally is this command's
                # entire contract — the operator runs it precisely because something is
                # already wrong — so one failing row is a skip, not an abort that leaves
                # an arbitrary prefix of rows filled and prints no count at all.
                logger.exception(
                    "Could not backfill track statistics", extra={"track_id": track.pk}
                )
                refilled = False

            if refilled:
                filled += 1
            else:
                skipped += 1
                # The helper has already logged the exception with its own detail. This
                # line is for whoever is watching the terminal, and names the row by the
                # filename the rider would recognise rather than by pk alone.
                self.stderr.write(f"Skipped track {track.pk} ({track.original_filename}).")

        self.stdout.write(self.style.SUCCESS(f"Filled {filled}, skipped {skipped}."))
