"""The `post_delete` receiver that removes a track's file, on every path that deletes one.

Every test here wraps the deleting call in `django_capture_on_commit_callbacks(execute=True)`.
The receiver schedules the storage delete through `transaction.on_commit`, and
pytest-django wraps each test in a transaction that never commits — so without the
capture the deferred callback is silently skipped and the assertion passes while proving
nothing about it.
"""

import pytest
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.db import transaction
from pytest_django.fixtures import DjangoCaptureOnCommitCallbacks

from gpx.models import GpxTrack
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
