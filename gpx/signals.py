"""Storage cleanup for deleted `GpxTrack` rows, wired as a `post_delete` receiver.

Nothing calls into this module by name — `GpxConfig.ready` imports it so the `@receiver`
below runs. That placement is what makes cleanup a property of the *model* rather than of
one view: a trip cascade, the admin's `delete_selected` bulk action, an upload replacing
its predecessor and any future `QuerySet.delete()` all go through it.
"""

import logging
from functools import partial
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from gpx.models import GpxTrack

logger = logging.getLogger(__name__)


def discard_track_file(track: GpxTrack) -> None:
    """Delete a deleted track's file, never letting the attempt fail the request.

    This runs from `on_commit`, which fires synchronously as the outermost `atomic()`
    exits — inside the request, after the deletion has already committed. An exception
    escaping here would give the user a 500 for an operation the database has accepted,
    which is the one response that cannot be true. `FileSystemStorage.delete` absorbs a
    missing file on its own but nothing else, so an unmounted Volume or a permission
    change on the media directory would do exactly that.

    The catch is deliberately `Exception`, not `OSError`: `FileSystemStorage.delete`
    resolves the key through `safe_join` before it touches the filesystem, which raises
    `SuspiciousFileOperation`, and a remote backend raises its own client error — neither is
    an `OSError`, and either one escaping would produce exactly the 500 this guard exists to
    prevent. Fire-and-forget post-commit cleanup has no failure it could usefully re-raise,
    so the broad catch is what matches the contract stated above; `logger.exception` is what
    stops a programming error in here from vanishing with it.

    Swallowing it silently would leave orphan files accumulating with nothing to show
    for them, so the failure is logged rather than dropped.
    """
    try:
        track.file.delete(save=False)
    except Exception:
        logger.exception(
            "Could not delete track file",
            extra={"track_id": track.pk, "storage_key": track.file.name},
        )


@receiver(post_delete, sender=GpxTrack)
def discard_file_of_deleted_track(
    sender: type[GpxTrack], instance: GpxTrack, **kwargs: Any
) -> None:
    """Schedule a deleted track's file for removal once the transaction commits.

    Registering this receiver at all is the load-bearing half. `Collector.can_fast_delete`
    returns `False` for any model with `pre_delete`/`post_delete` listeners
    (`django/db/models/deletion.py:186-206`), so a `Trip.delete()` cascade now
    materializes its `GpxTrack` rows instead of erasing them in one SQL statement that
    never produces an instance to read a file path from. Without the receiver there is
    nothing for a receiver to be called with.

    The delete is scheduled, never performed inline: `post_delete` fires *inside* the
    collector's transaction, and storage deletes do not participate in it. A file removed
    there is already gone if the block later raises, which rolls the row back into
    existence pointing at a file that no longer exists — the silent partial-delete state
    the mitigation exists to prevent. Deferring to commit also means a rolled-back delete
    never fires the callback, so the file correctly survives.

    Strictly stronger than the explicit `on_commit` call it replaced in
    `GpxUploadView.form_valid`: this fires once per row *actually deleted*, so the set of
    files cleaned up equals the set of rows removed by construction. Review finding F2
    (`impl-review-phase-4.md:98-114`) had to enforce that equality by hand, because the
    view computed its cleanup set separately from its delete.
    """
    transaction.on_commit(partial(discard_track_file, instance))
