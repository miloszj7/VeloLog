"""The two receivers that remove a track's file: on every path that deletes a row, and on
every path that replaces the file on a row that stays.

Every test here wraps the mutating call in `django_capture_on_commit_callbacks(execute=True)`.
Both receivers schedule the storage delete through `transaction.on_commit`, and
pytest-django wraps each test in a transaction that never commits — so without the
capture the deferred callback is silently skipped and the assertion passes while proving
nothing about it.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from pytest_django.fixtures import DjangoAssertNumQueries, DjangoCaptureOnCommitCallbacks

from gpx.models import GpxTrack
from gpx.signals import discard_superseded_file_of_saved_track
from tests.conftest import StoredTrackFactory
from trips.models import Trip


def stored_name(track: GpxTrack) -> str:
    """Return a track's storage key, narrowing away `FieldFile.name`'s optional.

    A `None` here would mean the file never reached storage at all, so asserting it is
    the assertion the caller wanted anyway.
    """
    name = track.file.name
    assert name is not None
    return name


@pytest.mark.django_db
def test_deleting_a_track_removes_its_file(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The plain `Model.delete()` path, which no view exercises."""
    track = make_stored_track(trip)
    name = stored_name(track)
    assert default_storage.exists(name)

    with django_capture_on_commit_callbacks(execute=True):
        track.delete()

    assert not default_storage.exists(name)


@pytest.mark.django_db
def test_a_queryset_delete_removes_every_track_file(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """`QuerySet.delete()` never calls `Model.delete()`, so only a signal reaches it.

    Two tracks rather than one because `GpxTrack.trip` is a `ForeignKey`, not a
    `OneToOneField` — one-track-per-trip is a rule the upload view enforces, not one the
    schema does, so N tracks is the shape any deletion path has to survive. A receiver
    that fired once per *queryset* rather than once per row would pass with one track and
    strand the second file here.
    """
    first = make_stored_track(trip, content=b"<gpx>1</gpx>", original_filename="day-1.gpx")
    second = make_stored_track(trip, content=b"<gpx>2</gpx>", original_filename="day-2.gpx")
    names = [stored_name(first), stored_name(second)]
    assert all(default_storage.exists(name) for name in names)

    with django_capture_on_commit_callbacks(execute=True):
        GpxTrack.objects.all().delete()

    assert GpxTrack.objects.count() == 0
    assert not any(default_storage.exists(name) for name in names)


@pytest.mark.django_db
def test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The admin's **Delete selected trips** path: a cascade from a `Trip` queryset.

    Nothing here touches `GpxTrack` between creating it and asserting its file is gone —
    the collector is what has to materialize the row. Registering the receiver is exactly
    what makes it: `Collector.can_fast_delete` returns `False` for a model with
    `post_delete` listeners, so the cascade stops being one row-less bulk `DELETE` and
    starts producing instances with a storage key on them.
    """
    name = stored_name(make_stored_track(trip))
    assert default_storage.exists(name)

    with django_capture_on_commit_callbacks(execute=True):
        Trip.objects.filter(pk=trip.pk).delete()

    assert GpxTrack.objects.count() == 0
    assert not default_storage.exists(name)


@pytest.mark.django_db
def test_a_user_queryset_cascade_removes_the_track_files_two_levels_down(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The admin's **Delete selected users** path: a cascade two levels deep.

    `Trip.owner` and `GpxTrack.trip` are both `CASCADE`, so deleting the owning `User`
    has to materialize the intervening `Trip` *and* the `GpxTrack` beneath it, reclaiming
    the file the same way the one-level `Trip` queryset cascade above already does.
    """
    name = stored_name(make_stored_track(trip))
    assert default_storage.exists(name)

    with django_capture_on_commit_callbacks(execute=True):
        User.objects.filter(pk=trip.owner_id).delete()

    assert GpxTrack.objects.count() == 0
    assert not default_storage.exists(name)


@pytest.mark.django_db
def test_a_cleanup_failure_does_not_fail_a_delete_that_already_committed(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unmounted volume must not turn a committed delete into a 500.

    The callback runs inside the request, after the commit. Left unguarded, a storage
    error there gives the user a failure for a deletion the database has already
    accepted — a response that contradicts the state of the system. The orphaned file is
    the cost; the wrong answer is not.

    The log line is asserted, not just the absence of an exception: an orphan file that is
    swallowed silently is indistinguishable from no orphan at all, so the record is the
    only thing an operator has. `track_id` in particular has to be captured before the
    callback runs — the collector nulls every deleted instance's pk once the signals have
    fired, so a callback that read it at commit time would log `None`.
    """

    def refuse_delete(self: object, name: str) -> None:
        raise PermissionError(name)

    track = make_stored_track(trip)
    name = stored_name(track)
    pk = track.pk
    monkeypatch.setattr(
        "django.core.files.storage.FileSystemStorage.delete", refuse_delete, raising=True
    )

    with caplog.at_level("ERROR", logger="gpx.signals"):
        with django_capture_on_commit_callbacks(execute=True):
            track.delete()

    assert not GpxTrack.objects.filter(pk=pk).exists()
    # The row is gone either way; only the file survives the refusal.
    assert default_storage.exists(name)
    # Read through `__dict__`: `logger.exception(..., extra={...})` stamps these onto the
    # record dynamically, so they are not attributes `LogRecord` declares.
    (record,) = caplog.records
    assert record.__dict__["track_id"] == pk
    assert record.__dict__["storage_key"] == name


@pytest.mark.django_db
def test_a_non_oserror_from_storage_is_absorbed_too(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal above is an `OSError`; the ones that actually reach here need not be.

    `FileSystemStorage.delete` resolves the key through `safe_join` before it touches the
    filesystem, so a key that escapes `MEDIA_ROOT` raises `SuspiciousFileOperation`, and a
    remote backend raises its own client error — neither inherits `OSError`. A guard written
    against `OSError` alone lets both straight through and turns a committed delete into a
    500, which is the one thing this receiver promises never to do. The test above cannot
    catch that narrowing, because `PermissionError` *is* an `OSError`.
    """

    def refuse_delete(self: object, name: str) -> None:
        raise SuspiciousFileOperation(name)

    track = make_stored_track(trip)
    name = stored_name(track)
    pk = track.pk
    monkeypatch.setattr(
        "django.core.files.storage.FileSystemStorage.delete", refuse_delete, raising=True
    )

    with django_capture_on_commit_callbacks(execute=True):
        track.delete()

    assert not GpxTrack.objects.filter(pk=pk).exists()
    assert default_storage.exists(name)


@pytest.mark.django_db
def test_deleting_a_row_with_no_stored_file_schedules_nothing(
    trip: Trip,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """A row whose file never reached storage has no key worth a callback.

    `FieldFile.delete` early-returns on an empty name, so absorbing this was free while the
    callback took the instance. A callback that takes a storage key has to decline in the
    receiver instead, or it asks storage to delete `""` — and `FileSystemStorage.delete`
    raises `ValueError` on an empty name rather than shrugging.
    """
    track = GpxTrack.objects.create(
        trip=trip,
        file="",
        points=[],
        min_latitude=0.0,
        min_longitude=0.0,
        max_latitude=0.0,
        max_longitude=0.0,
        original_filename="never-stored.gpx",
    )

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        track.delete()

    assert callbacks == []


@pytest.mark.django_db
def test_a_rolled_back_delete_leaves_the_file_in_place(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """This is the property that makes `on_commit` the right hook rather than an inline delete.

    `post_delete` fires *inside* the collector's transaction, and storage deletes do not
    participate in it. A receiver that deleted the file where it stands would already have
    destroyed it by the time the block below raises — and the rollback then restores the
    row pointing at a file that no longer exists, which is precisely the silent
    partial-delete state the mitigation exists to prevent. Deferring to commit means the
    callback is discarded with the savepoint instead.
    """
    track = make_stored_track(trip)
    name = stored_name(track)
    pk = track.pk

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                track.delete()
                raise RuntimeError("something later in the block failed")

    assert callbacks == []
    assert GpxTrack.objects.filter(pk=pk).exists()
    assert default_storage.exists(name)


@pytest.mark.django_db
def test_replacing_a_stored_file_removes_the_predecessor(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The strand `post_delete` structurally cannot reach: the row survives the replacement.

    `gpx_upload_path` mints fresh random bytes per write, so the successor can never
    overwrite the predecessor in place — without the `pre_save` receiver the old file just
    stays there, referenced by nothing, on every admin repair.
    """
    track = make_stored_track(trip)
    predecessor = stored_name(track)
    assert default_storage.exists(predecessor)

    with django_capture_on_commit_callbacks(execute=True):
        track.file.save("day-2.gpx", ContentFile(b"<gpx>2</gpx>"), save=True)

    successor = stored_name(track)
    assert successor != predecessor
    assert default_storage.exists(successor)
    assert not default_storage.exists(predecessor)


@pytest.mark.django_db
def test_saving_a_track_without_touching_its_file_removes_nothing(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The ordinary edit — and the shape a change form submitted with no new file takes.

    `forms.FileField.clean` returns `initial` when the widget was left alone, i.e. the
    already-committed `FieldFile`, so the stored key and `instance.file.name` are equal.
    A receiver that skipped that comparison would delete the file on every save.
    """
    track = make_stored_track(trip)
    name = stored_name(track)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        track.original_filename = "renamed.gpx"
        track.save()

    assert callbacks == []
    assert default_storage.exists(name)


@pytest.mark.django_db
def test_a_save_whose_update_fields_exclude_the_file_removes_nothing(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """`update_fields` is checked before the query, so a stats save costs nothing.

    The in-memory field is deliberately pointed somewhere else first: that is what makes
    this prove the `update_fields` guard rather than the key comparison further down. The
    column named in `update_fields` is the only one the `UPDATE` can touch, so the
    divergent `file` value never reaches the database either.
    """
    track = make_stored_track(trip)
    name = stored_name(track)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        track.file = "gpx/1/1/somewhere-else.gpx"
        track.save(update_fields=["original_filename"])

    assert callbacks == []
    assert default_storage.exists(name)
    track.refresh_from_db()
    assert stored_name(track) == name


@pytest.mark.django_db
def test_the_insert_path_costs_the_receiver_no_query(
    trip: Trip,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """`signals.py:163` claims the insert path "costs the hot path zero queries".

    `instance.pk is None` is checked before the predecessor lookup, so calling the
    receiver directly on an unsaved instance must not touch the database at all.
    """
    unsaved = GpxTrack(trip=trip, file="gpx/1/1/new.gpx", original_filename="new.gpx")

    with django_assert_num_queries(0):
        discard_superseded_file_of_saved_track(GpxTrack, instance=unsaved)


@pytest.mark.django_db
def test_the_update_fields_guard_costs_the_receiver_no_query(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """`signals.py:168` claims a save excluding `file` "is answered without a query".

    The `update_fields` guard runs before the predecessor lookup, so calling the receiver
    directly with `update_fields` excluding `file` must not touch the database at all.
    """
    track = make_stored_track(trip)

    with django_assert_num_queries(0):
        discard_superseded_file_of_saved_track(
            GpxTrack, instance=track, update_fields=frozenset({"original_filename"})
        )


@pytest.mark.django_db
def test_a_rolled_back_replacement_leaves_the_predecessor_in_place(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The mirror of the rolled-back-delete case, and why this defers to commit too.

    A receiver that deleted the predecessor where it stands would have destroyed it before
    the block below raises — and the rollback then restores a row still pointing at that
    file, turning a failed edit into a track whose download 404s.
    """
    track = make_stored_track(trip)
    predecessor = stored_name(track)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                track.file.save("day-2.gpx", ContentFile(b"<gpx>2</gpx>"), save=True)
                raise RuntimeError("something later in the block failed")

    assert callbacks == []
    track.refresh_from_db()
    assert stored_name(track) == predecessor
    assert default_storage.exists(predecessor)


@pytest.mark.django_db
def test_a_first_save_onto_a_row_with_no_stored_file_schedules_nothing(
    trip: Trip,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """An empty stored key is not a predecessor — and this is the `make_stored_track` idiom.

    `GpxTrack.objects.create(...)` followed by `file.save(..., save=True)` is an `UPDATE`
    on an existing row, so it reaches the replacement receiver with a pk set. Its stored
    key is `""`, and asking storage to delete `""` raises `ValueError` rather than
    shrugging, so the falsy guard is what keeps the fixture itself working.
    """
    track = GpxTrack.objects.create(
        trip=trip,
        file="",
        points=[],
        min_latitude=0.0,
        min_longitude=0.0,
        max_latitude=0.0,
        max_longitude=0.0,
        original_filename="first-upload.gpx",
    )

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        track.file.save("first-upload.gpx", ContentFile(b"<gpx/>"), save=True)

    assert callbacks == []
    assert default_storage.exists(stored_name(track))


@pytest.mark.django_db
def test_a_raw_save_never_reclaims_anything(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """`loaddata` replays rows as serialized; that is a restore, not a replacement.

    A raw save is the one case where a differing key means the opposite of what it means
    everywhere else — the fixture is asserting what the row should point at, and the file
    it names may well be the one already on the volume. Reclaiming there would delete part
    of what the load is restoring, so the guard fires before the comparison ever runs.
    `save_base(raw=True)` is what `loaddata` calls; nothing else in Django sets the flag.
    """
    track = make_stored_track(trip)
    name = stored_name(track)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        track.file = "gpx/1/1/from-a-fixture.gpx"
        track.save_base(raw=True)

    assert callbacks == []
    assert default_storage.exists(name)


@pytest.mark.django_db
def test_pre_save_removes_nothing_when_a_sibling_stage_is_inserted(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """ADD semantics' correctness argument, pinned as an assertion.

    `gpx/views.py`'s docstring argues that inserting a second stage never touches the
    first stage's file, because `pre_save` returns immediately for any row whose `pk` is
    still `None`. This is that argument made concrete: two stages end up on one trip and
    the first one's file survives, with nothing scheduled for it.
    """
    first = make_stored_track(trip, content=b"<gpx>1</gpx>", original_filename="day-1.gpx")
    first_name = stored_name(first)
    assert default_storage.exists(first_name)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        second = GpxTrack.objects.create(
            trip=trip,
            file="gpx/1/1/inserted.gpx",
            points=[],
            min_latitude=0.0,
            min_longitude=0.0,
            max_latitude=0.0,
            max_longitude=0.0,
            original_filename="day-2.gpx",
        )

    assert callbacks == []
    assert GpxTrack.objects.filter(trip=trip).count() == 2
    assert default_storage.exists(first_name)
    assert GpxTrack.objects.filter(pk=second.pk).exists()


@pytest.mark.django_db
def test_deleting_one_stage_removes_only_its_own_file(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Two live stages on one trip, and a delete scoped to only one of them.

    `post_delete` is row-scoped by construction, but ADD semantics is the first place two
    stages on one trip is a shape a test builds directly rather than through a replace.
    """
    first = make_stored_track(trip, content=b"<gpx>1</gpx>", original_filename="day-1.gpx")
    second = make_stored_track(trip, content=b"<gpx>2</gpx>", original_filename="day-2.gpx")
    first_name, second_name = stored_name(first), stored_name(second)

    with django_capture_on_commit_callbacks(execute=True):
        first.delete()

    assert not default_storage.exists(first_name)
    assert default_storage.exists(second_name)
    assert GpxTrack.objects.filter(pk=second.pk).exists()


@pytest.mark.django_db
def test_a_cleanup_failure_does_not_fail_a_replacement_that_already_committed(
    trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Same contract as the delete case: the row is committed, so the request cannot 500.

    The log line is the whole remedy here — the predecessor stays on the volume and the
    key named in `storage_key` is what an operator feeds back to `reconcile_media`. It has
    to be the *superseded* key, not the one the row now points at, or the line names a
    file that is still in use.
    """

    def refuse_delete(self: object, name: str) -> None:
        raise PermissionError(name)

    track = make_stored_track(trip)
    predecessor = stored_name(track)
    pk = track.pk
    monkeypatch.setattr(
        "django.core.files.storage.FileSystemStorage.delete", refuse_delete, raising=True
    )

    with caplog.at_level("ERROR", logger="gpx.signals"):
        with django_capture_on_commit_callbacks(execute=True):
            track.file.save("day-2.gpx", ContentFile(b"<gpx>2</gpx>"), save=True)

    assert stored_name(track) != predecessor
    assert default_storage.exists(predecessor)
    (record,) = caplog.records
    assert record.__dict__["track_id"] == pk
    assert record.__dict__["storage_key"] == predecessor
