"""Storage cleanup for `GpxTrack` files, wired as `post_delete` and `pre_save` receivers.

Nothing calls into this module by name — `GpxConfig.ready` imports it so the `@receiver`
decorators below run. That placement is what makes cleanup a property of the *model*
rather than of one view or one `ModelAdmin`: a trip cascade, the admin's `delete_selected`
bulk action, an upload replacing its predecessor, a bare `QuerySet.delete()` and a file
replaced on a row that stays all go through this module.

The two receivers split the lifecycle between them. `post_delete` covers a file whose row
is gone; `pre_save` covers a file superseded on a row that survives, which is what the
admin change form does. Both schedule their storage work with `transaction.on_commit`,
never inline, for the reason `discard_file_by_key` gives.
"""

import logging
from functools import partial
from typing import Any

from django.core.files.storage import Storage
from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from gpx.models import GpxTrack

logger = logging.getLogger(__name__)


def discard_file_by_key(track_pk: int, storage_key: str, storage: Storage) -> None:
    """Delete a track's file by storage key, never failing the request for it.

    Both receivers below share this body, because the two cases they cover want exactly
    the same thing done: `discard_file_of_deleted_track` hands it the key of a row that is
    gone, and `discard_superseded_file_of_saved_track` hands it the key a surviving row
    used to point at. Neither has a caller left to raise at by the time it runs.

    Scalars rather than the instance, on purpose. Registering this module's receiver makes
    `Collector` skip its field-deferral optimization for any model with listeners
    (`django/db/models/deletion.py:325-337`), so a cascade already `SELECT`s whole
    `GpxTrack` rows — `points` included, which `gpx/constants.py` caps at
    `MAX_GPX_POINTS = 100_000`. Closing over the instance would hold every one of those
    rows resident *past* commit as well; closing over a key lets the collector's list go as
    the transaction ends. An admin `delete_selected` over a season of trips is the path
    where the difference is measured in megabytes.

    The pk is read in the receiver and passed in for the same reason it cannot be read
    here: the collector nulls out each deleted instance's pk (`deletion.py:455`) once the
    signals have fired, so a callback reading `track.pk` at commit time logs `None`.

    This runs from `on_commit`, which fires synchronously as the outermost `atomic()`
    exits — inside the request, after the deletion or save has already committed. An
    exception escaping here would give the user a 500 for an operation the database has
    accepted, which is the one response that cannot be true. `FileSystemStorage.delete`
    absorbs a missing file on its own but nothing else, so an unmounted Volume or a
    permission change on the media directory would do exactly that.

    The catch is deliberately `Exception`, not `OSError`: `FileSystemStorage.delete`
    resolves the key through `safe_join` before it touches the filesystem, which raises
    `SuspiciousFileOperation`, and a remote backend raises its own client error — neither is
    an `OSError`, and either one escaping would produce exactly the 500 this guard exists to
    prevent. Fire-and-forget post-commit cleanup has no failure it could usefully re-raise,
    so the broad catch is what matches the contract stated above; `logger.exception` is what
    stops a programming error in here from vanishing with it.

    Swallowing it silently would leave orphan files accumulating with nothing to show
    for them, so the failure is logged rather than dropped. The message names both cases
    the key can come from: after a failed *replacement* the row is still there, and a line
    reading "deleted track" would send an operator looking for a row that never went away.
    `reconcile_media` is what reclaims whatever this line reports.
    """
    try:
        storage.delete(storage_key)
    except Exception:
        logger.exception(
            "Could not delete a superseded or deleted track's file",
            extra={"track_id": track_pk, "storage_key": storage_key},
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
    storage_key = instance.file.name
    if not storage_key:
        # `FieldFile.delete` used to absorb this for free; a key-based callback has to
        # decline explicitly rather than ask storage to delete "". Nothing was stored.
        return
    transaction.on_commit(
        partial(discard_file_by_key, instance.pk, storage_key, instance.file.storage)
    )


@receiver(pre_save, sender=GpxTrack)
def discard_superseded_file_of_saved_track(
    sender: type[GpxTrack], instance: GpxTrack, **kwargs: Any
) -> None:
    """Schedule the predecessor for removal when an existing row's file is replaced.

    The gap this closes is the admin change form. `GpxTrackAdmin` excludes only `points`,
    so `file` renders as an editable upload widget on the documented repair path;
    `FileField.save_form_data` sets the new value without consulting the old one, the row
    is `UPDATE`d rather than deleted, and `post_delete` never fires. `gpx_upload_path`
    mints a fresh `secrets.token_hex(16)` per write, so the new key can never overwrite
    the old — the predecessor is stranded deterministically, not occasionally.

    `pre_save` rather than `post_save`, because the old key has to be read while it is
    still the one in the database. `Model.save_base` sends `pre_save`
    (`django/db/models/base.py:946-952`) *before* entering `_save_table`, where
    `FileField.pre_save` (`fields/files.py:325-339`) commits the upload to storage and only
    then makes `self.name` the final key. So at this point the row still holds the
    predecessor and the query below is the only place it can be read from.

    `old_key != instance.file.name` is the whole predicate, and it holds in each shape the
    field can be in at this moment:

    - *A new file through a form* — `save_form_data` has set `file` to the `UploadedFile`,
      whose name is a bare browser basename. A stored key is always three levels deep
      (`gpx/<owner>/<trip>/<32hex>.gpx`), so the two can never compare equal.
    - *A form submitted with no new file* — `forms.FileField.clean` returns `initial`, the
      already-committed `FieldFile`, so the names match and this returns.
    - *The field cleared* — `save_form_data` stores `""` (`files.py:368`, `data or ""`),
      which differs from the old key, so the predecessor is correctly reclaimed.
    - *`FieldFile.save(name, content, save=True)`* — the file is committed and `name` is
      already final before `instance.save()` runs, so the comparison still holds.

    Deferring to commit is what makes a rolled-back replacement leave the predecessor
    alone, for the same reason the delete receiver defers: see `discard_file_by_key`.

    Named limitation, not an omission: `bulk_create`, `bulk_update` and `QuerySet.update`
    do not send `pre_save` at all, by design. Nor does process death between the storage
    write and the commit. `manage.py reconcile_media` is the backstop for those.
    """
    if kwargs.get("raw"):
        # Fixture loading replays rows as they were serialized; it is not a replacement,
        # and deleting the file a `loaddata` row names would destroy what it restores.
        return
    if instance.pk is None:
        # The insert path — every upload. Returning here is what keeps this receiver off
        # `GpxUploadView.form_valid`, whose superseded rows are *deleted* and so already
        # covered by `discard_file_of_deleted_track`, and costs the hot path zero queries.
        return
    update_fields = kwargs.get("update_fields")
    if update_fields is not None and "file" not in update_fields:
        # A save that cannot have touched `file` — `gpx/statistics.py` saves only the
        # statistics columns this way — is answered without a query.
        return

    # Deferred to the one column, so the `points` blob is never loaded to answer this.
    old_key: str | None = (
        GpxTrack.objects.filter(pk=instance.pk).values_list("file", flat=True).first()
    )
    if not old_key:
        # `None`: a pk was assigned by the caller and the row is not in the database yet,
        # so this save is an insert wearing an update's shape. `""`: nothing was stored.
        return
    if old_key == instance.file.name:
        return

    transaction.on_commit(partial(discard_file_by_key, instance.pk, old_key, instance.file.storage))
