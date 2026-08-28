"""`manage.py reconcile_media` — the project's only way to see an unreferenced media file.

Every other filesystem touch in this codebase is keyed by an exact name read from the
database, so until this command existed nothing in the application could enumerate
`MEDIA_ROOT` at all and the question "is anything stranded on the volume?" could only be
answered by walking the Railway CLI by hand and downloading the production database.

Two layers cover the orphan class and this is the second one. `gpx/signals.py` prevents the
sources that go through `Model.save()` and `Model.delete()`; this reclaims what prevention
structurally cannot reach — process death between the storage write and the commit,
`bulk_create` / `bulk_update` / `QuerySet.update` (which send no model signals by design),
files an ops restore wrote that no application code ever touched, and every orphan that
already exists.

Report-only by default, because `--delete` is the one irreversible action in this change:
there is no undo on a Volume. Three things guard it — the age threshold, the refusal when
nothing on the volume is referenced, and the flag itself.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from gpx.constants import ORPHAN_MIN_AGE_MINUTES
from gpx.models import GpxTrack

logger = logging.getLogger(__name__)


def _join(prefix: str, name: str) -> str:
    """Join a storage prefix and a bare name with the separator storage keys use.

    Forward slash, never `os.path.join`: these are storage keys, not filesystem paths, and
    `FileField` stores them with forward slashes on every platform.
    """
    return f"{prefix}/{name}" if prefix else name


def _is_walkable_directory(key: str) -> bool:
    """Return whether a directory key is a real directory inside `MEDIA_ROOT`.

    `Storage.listdir` classifies entries with `entry.is_dir()`, which follows symlinks, and
    `safe_join` — the containment check behind `FileSystemStorage.path` — compares `abspath`
    and never `realpath` (`django/utils/_os.py:65-92`). A symlinked directory therefore
    passes that check, and `FileSystemStorage.delete`'s `os.remove` then follows the
    symlinked *parent* and unlinks the real file behind it. So `ln -s /data/backups
    /data/media/archive` would have this command reclaim the backups themselves.

    Both halves of the test are load-bearing and neither subsumes the other:

    - `is_symlink()` is what bounds the recursion. A self-referential link (`ln -s . loop`)
      resolves to `MEDIA_ROOT`, which *is* inside `MEDIA_ROOT`, so containment alone would
      recurse `loop/loop/loop/…` without limit. Every loop needs a symlink; refusing to
      descend through one is what makes the walk terminate.
    - Resolving both sides is what catches an escape that is not a symlink — a bind mount,
      or a junction on Windows — where the entry is a genuine directory whose contents live
      somewhere else entirely.

    A symlinked file needs no such guard: `os.remove` on a symlink unlinks the link, not its
    target, so only the directory case can reach outside the volume.
    """
    try:
        path = Path(default_storage.path(key))
    except SuspiciousFileOperation, NotImplementedError, ValueError:
        return False
    try:
        if path.is_symlink():
            return False
        return path.resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve())
    except OSError:
        return False


def walk_storage(prefix: str = "") -> tuple[list[str], list[str]]:
    """Return every file key and every directory key under `prefix`.

    Args:
        prefix: The storage key to walk from. `""` is `MEDIA_ROOT` itself.

    Returns:
        `(file_keys, directory_keys)`. Directory keys are **deepest-first**, because that
        is the only order in which pruning can reach anything: a parent is empty only once
        its children are gone. `MEDIA_ROOT` itself is never in the list — it is not a
        candidate for removal under any flag.

    `Storage.listdir` does not recurse and returns bare names, so the recursion and the
    joining are both the caller's job. It raises `FileNotFoundError` from `os.scandir` when
    the directory is absent; a missing `MEDIA_ROOT` is an ordinary state on a fresh
    deployment that has taken no uploads yet, so it reports empty rather than crashing.
    """
    try:
        directories, files = default_storage.listdir(prefix)
    except FileNotFoundError:
        return [], []

    file_keys = [_join(prefix, name) for name in files]
    directory_keys: list[str] = []
    for name in sorted(directories):
        child = _join(prefix, name)
        if not _is_walkable_directory(child):
            # `logger.warning` rather than a `self.stderr` line: this is not a per-item
            # finding but a refusal to look, and the production root logger sits at
            # WARNING, so it reaches `railway logs` where an operator will see it.
            logger.warning(
                "Refusing to walk a media directory that leaves MEDIA_ROOT",
                extra={"storage_key": child},
            )
            continue
        child_files, child_directories = walk_storage(child)
        file_keys.extend(child_files)
        # The child's own subdirectories precede it, which is what makes the whole list
        # deepest-first once the recursion unwinds.
        directory_keys.extend(child_directories)
        directory_keys.append(child)
    return sorted(file_keys), directory_keys


class Command(BaseCommand):
    help = (
        "Report files under MEDIA_ROOT that no GpxTrack row references. "
        "With --delete, reclaim them and prune the directories they leave empty."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Reclaim the orphans found rather than only reporting them.",
        )
        parser.add_argument(
            "--min-age-minutes",
            type=int,
            default=ORPHAN_MIN_AGE_MINUTES,
            help=(
                "Spare files modified more recently than this, since a file written "
                "seconds ago may belong to a request still in flight. 0 disables the "
                "guard and is only safe on an idle service. "
                f"Default: {ORPHAN_MIN_AGE_MINUTES}."
            ),
        )
        parser.add_argument(
            "--allow-full-sweep",
            action="store_true",
            help=(
                "Permit --delete even when nothing on the volume is referenced. Only "
                "correct when the database really is empty; never as a way past an "
                "unexpected refusal."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Walk, classify, optionally reclaim, and always print a tally.

        Reports through both of the channels `backfill_gpx_stats` uses — per-item lines on
        stderr and a final tally on stdout — rather than through `logger.info`, because the
        production root logger sits at `WARNING` and an operator watching `railway logs`
        would see nothing at all.

        Always exits 0. A per-item failure is a counted skip: an operator runs this
        precisely when something is already wrong, and an abort halfway through would
        leave an arbitrary prefix of files reclaimed and print no count at all.
        """
        reclaim: bool = options["delete"]
        min_age: int = options["min_age_minutes"]
        allow_full_sweep: bool = options["allow_full_sweep"]

        found, directories = walk_storage()
        referenced = {key for key in GpxTrack.objects.values_list("file", flat=True) if key}

        # Every mtime this command acts on is read here, before anything is removed.
        # Reading a directory's mtime *after* reclaiming a file inside it would read the
        # timestamp of this command's own delete and spare every directory it just
        # emptied — the age guard has to describe the volume as it was found.
        cutoff = timezone.now() - timedelta(minutes=min_age)

        orphans: list[str] = []
        referenced_here = 0
        spared = 0
        for key in found:
            if key in referenced:
                referenced_here += 1
                continue
            modified, size = self._stat(key)
            if modified is None:
                spared += 1
                self.stderr.write(f"Spared {key}: it could not be read.")
                continue
            if modified > cutoff:
                spared += 1
                self.stderr.write(f"Spared {key}: modified in the last {min_age} minute(s).")
                continue
            orphans.append(key)
            self.stderr.write(f"Orphan {key} ({size} bytes).")

        prunable = self._empty_directories(directories, found, set(orphans), cutoff, min_age)

        refused = self._warn_on_skew(found, referenced_here, reclaim, allow_full_sweep)

        reclaimed = 0
        skipped = 0
        pruned = 0
        if reclaim and not refused:
            reclaimed, skipped = self._reclaim(orphans)
            pruned, pruning_skipped = self._prune(prunable)
            skipped += pruning_skipped

        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {len(found)}, referenced {referenced_here}, "
                f"orphaned {len(orphans)}, spared {spared}, reclaimed {reclaimed}, "
                f"skipped {skipped}, directories pruned {pruned}."
            )
        )
        if not reclaim:
            self.stdout.write(
                "Nothing was removed. This is a report; re-run with --delete to reclaim."
            )

    def _empty_directories(
        self,
        directories: list[str],
        found: list[str],
        orphans: set[str],
        cutoff: datetime,
        min_age: int,
    ) -> list[str]:
        """Name the directories that hold nothing once the orphans are gone, deepest-first.

        Emptiness is derived from the walk rather than probed, so that report-only mode can
        *preview* it: a directory holding only orphans is not empty yet, but it is exactly
        what an operator running without `--delete` needs to be told about. The four empty
        `gpx/<owner>/<trip>/` directories on the local volume are the case this exists for
        — they hold no files at all, so no orphan report would ever mention them.

        A directory is reported only if it also clears the age guard, because a directory
        is as capable of being in flight as a file is: `FileSystemStorage._save` calls
        `os.makedirs` and only then opens the file inside it, so a prune landing in that
        window removes the directory an upload is about to write into and the upload 500s.
        """
        surviving = [key for key in found if key not in orphans]
        prunable: list[str] = []
        for key in directories:
            prefix = f"{key}/"
            if any(survivor.startswith(prefix) for survivor in surviving):
                continue
            modified, _ = self._stat(key)
            if modified is None or modified > cutoff:
                self.stderr.write(
                    f"Spared directory {key}: modified in the last {min_age} minute(s)."
                )
                continue
            self.stderr.write(f"Empty directory {key}.")
            prunable.append(key)
        return prunable

    def _stat(self, key: str) -> tuple[datetime | None, int]:
        """Return a key's modification time and size, or `(None, 0)` if it cannot be read.

        A file or directory that vanished between the walk and this read is not an error
        worth aborting for — it is the ordinary outcome of reconciling a live volume, and
        a candidate that no longer exists needs no reclaiming. Treating it as unreadable
        spares it, which is the conservative direction.
        """
        try:
            return default_storage.get_modified_time(key), default_storage.size(key)
        except OSError:
            return None, 0

    def _warn_on_skew(
        self, found: list[str], referenced_here: int, reclaim: bool, allow_full_sweep: bool
    ) -> bool:
        """Warn when the volume and the database look like different points in time.

        `walk(MEDIA_ROOT) - set(GpxTrack.file)` names orphans only if both halves describe
        the same moment, and nothing in the walk can check that. Two states documented in
        this repo break it — a database restored without its media (`DEPLOY.md`), and a
        `MEDIA_ROOT` pointing at a tree this database does not describe, the one fault
        escalated to a Hard Rule. In both, every file looks orphaned and every one of them
        is older than any threshold by construction, so the age guard says nothing.

        Both produce one recognizable shape: files were found and not one is referenced.

        Returns:
            `True` if `--delete` must be refused. The refusal does not cover a *partial*
            restore, where surviving rows keep `referenced_here` above zero — that is what
            the operator precondition in `DEPLOY.md` is for.
        """
        if not found or referenced_here:
            return False

        self.stderr.write(
            f"WARNING: {len(found)} file(s) are on the volume and not one of them is "
            "referenced by a GpxTrack row."
        )
        self.stderr.write(
            "That is the shape of a database and a media volume taken from different "
            "points in time (a database restored without its media, or a MEDIA_ROOT "
            "pointing at a tree this database does not describe), rather than the shape "
            "of ordinary orphans. Reclaiming now would delete files that are still in use."
        )
        if not reclaim or allow_full_sweep:
            return False

        self.stderr.write(
            "Refusing --delete. Confirm the database and the volume are the same point in "
            "time; then, only if the database really is empty, re-run with "
            "--allow-full-sweep."
        )
        return True

    def _reclaim(self, orphans: list[str]) -> tuple[int, int]:
        """Delete each orphan, counting a failure rather than raising it.

        `FileSystemStorage.delete` absorbs `FileNotFoundError` on its own, which is what
        makes a second run over the same list a clean no-op instead of a crash.
        """
        reclaimed = 0
        skipped = 0
        for key in orphans:
            try:
                default_storage.delete(key)
            except Exception:
                logger.exception(
                    "Could not reclaim an orphaned media file", extra={"storage_key": key}
                )
                skipped += 1
                self.stderr.write(f"Could not reclaim {key}.")
            else:
                reclaimed += 1
        return reclaimed, skipped

    def _prune(self, directories: list[str]) -> tuple[int, int]:
        """Remove the directories left empty, deepest-first.

        Two protections, and both are load-bearing. The emptiness re-check is what keeps
        the tally meaningful — attempting every directory would make a populated one fail
        on every single run, drowning the real findings in noise. And the wrapped delete is
        what keeps a directory that became non-empty *between* that check and the removal
        from aborting the run: `FileSystemStorage.delete` calls `os.rmdir` on a directory
        and absorbs only `FileNotFoundError`, so `os.rmdir`'s refusal to remove a non-empty
        directory arrives here as an `OSError` that would otherwise escape `handle` after
        files have already been deleted and before the tally prints.

        `os.rmdir` refusing a non-empty directory is therefore the backstop rather than the
        filter — which is what makes over-reach impossible even if the check is wrong.
        """
        pruned = 0
        skipped = 0
        for key in directories:
            try:
                subdirectories, files = default_storage.listdir(key)
            except OSError:
                continue
            if subdirectories or files:
                continue
            try:
                default_storage.delete(key)
            except Exception:
                logger.exception(
                    "Could not prune an emptied media directory", extra={"storage_key": key}
                )
                skipped += 1
                self.stderr.write(f"Could not prune {key}.")
            else:
                pruned += 1
        return pruned, skipped
