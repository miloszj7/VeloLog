"""`manage.py backfill_gpx_stats` — the recovery path for a backfill that filled nothing.

Migration `0003` runs once, unattended, at container boot, and its most likely failure is
a misconfigured `MEDIA_ROOT` — the one operational fault this repo has escalated to a
Hard Rule in `AGENTS.md`, documented in `DEPLOY.md` and wired into `/healthz/`. If that
deploy is the deploy `0003` applies on, the migration reads no files, fills nothing, and
can never be re-run: a migration cannot be re-applied once recorded. This command is what
makes that one invocation to recover instead of re-uploading every file by hand.

It carries no computation of its own — every line of that lives in `gpx/statistics.py`,
the same helper the migration calls, so the two cannot drift.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from gpx.models import GpxTrack
from gpx.statistics import backfill_track_statistics


class Command(BaseCommand):
    help = "Recompute the statistics columns on stored GPX tracks from their files."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--all",
            action="store_true",
            help=(
                "Reprocess every track, not only those whose statistics are null — for a "
                "track whose file was replaced or whose stored figures are stale."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Refill the selected tracks and report a tally, exiting 0 even on skips.

        A partially unreadable media directory is exactly the situation this command
        exists for, so it is a report rather than a crash: the helper absorbs a row whose
        file cannot be read, and the tally is what tells the operator how many rows are
        still waiting on a corrected `MEDIA_ROOT`.
        """
        tracks = GpxTrack.objects.all()
        if not options["all"]:
            # The same probe the migration uses, and for the same reason: `distance_meters`
            # is the one statistic that is never null once computed, so the other three
            # would select rows whose file simply carried no `<ele>` or `<time>` over and
            # over again.
            tracks = tracks.filter(distance_meters__isnull=True)

        filled = 0
        skipped = 0
        for track in tracks.iterator():
            if backfill_track_statistics(track):
                filled += 1
            else:
                skipped += 1
                # The helper has already logged the exception with its own detail. This
                # line is for whoever is watching the terminal, and names the row by the
                # filename the rider would recognise rather than by pk alone.
                self.stderr.write(f"Skipped track {track.pk} ({track.original_filename}).")

        self.stdout.write(self.style.SUCCESS(f"Filled {filled}, skipped {skipped}."))
