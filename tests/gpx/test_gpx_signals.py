"""The `post_delete` receiver that removes a track's file, on every path that deletes one.

Every test here wraps the deleting call in `django_capture_on_commit_callbacks(execute=True)`.
The receiver schedules the storage delete through `transaction.on_commit`, and
pytest-django wraps each test in a transaction that never commits — so without the
capture the deferred callback is silently skipped and the assertion passes while proving
nothing about it.
"""

import pytest
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
) -> None:
    """An unmounted volume must not turn a committed delete into a 500.

    The callback runs inside the request, after the commit. Left unguarded, a storage
    error there gives the user a failure for a deletion the database has already
    accepted — a response that contradicts the state of the system. The orphaned file is
    the cost; the wrong answer is not.
    """

    def refuse_delete(self: object, name: str) -> None:
        raise PermissionError(name)

    track = make_stored_track(trip)
    name = stored_name(track)
    pk = track.pk
    monkeypatch.setattr(
        "django.core.files.storage.FileSystemStorage.delete", refuse_delete, raising=True
    )

    with django_capture_on_commit_callbacks(execute=True):
        track.delete()

    assert not GpxTrack.objects.filter(pk=pk).exists()
    # The row is gone either way; only the file survives the refusal.
    assert default_storage.exists(name)


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
