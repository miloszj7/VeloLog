import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from gpx.models import GpxTrack, gpx_upload_path
from tests.conftest import GPX_POINTS, TrackFactory
from trips.models import Trip


@pytest.fixture
def trip(rider: User) -> Trip:
    return Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)


@pytest.mark.django_db
def test_track_is_reachable_from_its_trip_via_reverse_accessor(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    track = make_gpx_track(trip)

    assert track in trip.tracks.all()


@pytest.mark.django_db
def test_deleting_a_trip_cascades_its_tracks(trip: Trip, make_gpx_track: TrackFactory) -> None:
    make_gpx_track(trip)

    trip.delete()

    # Rows only. Django has not deleted `FileField` files on model delete since 1.3, and
    # this slice does not add that behaviour — orphan cleanup is handed to S-04.
    assert GpxTrack.objects.count() == 0


@pytest.mark.django_db
def test_track_str_is_the_original_filename(trip: Trip, make_gpx_track: TrackFactory) -> None:
    track = make_gpx_track(trip, original_filename="pyrenees-stage-3.gpx")

    assert str(track) == "pyrenees-stage-3.gpx"


@pytest.mark.django_db
def test_upload_path_keeps_the_user_supplied_filename_off_disk(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    track = make_gpx_track(trip)

    path = gpx_upload_path(track, "../../../etc/passwd; rm -rf.gpx")

    assert "passwd" not in path
    assert ".." not in path
    assert not path.startswith("/")
    assert path.startswith(f"gpx/{trip.owner_id}/{trip.pk}/")
    assert path.endswith(".gpx")


@pytest.mark.django_db
def test_upload_path_is_unique_per_call_for_the_same_filename(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    track = make_gpx_track(trip)

    first = gpx_upload_path(track, "ride.gpx")
    second = gpx_upload_path(track, "ride.gpx")

    assert first != second


@pytest.mark.django_db
def test_tracks_come_back_newest_first(trip: Trip, make_gpx_track: TrackFactory) -> None:
    older = make_gpx_track(trip, original_filename="older.gpx")
    newer = make_gpx_track(trip, original_filename="newer.gpx")

    assert list(GpxTrack.objects.all()) == [newer, older]


@pytest.mark.django_db
def test_saving_through_the_field_routes_the_name_through_gpx_upload_path(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """`upload_to` must be wired to the field, not merely correct when called directly.

    Every other test here calls `gpx_upload_path` by hand, so dropping `upload_to=` from
    the field leaves them all green while the stored name reverts to the user's own —
    the exact property the function's docstring calls security-critical. This is the only
    test that saves real bytes through the descriptor and inspects what landed.

    The filename is deliberately *benign*. A traversal string would fail this test even
    with `upload_to` gone, because Django's own `get_valid_name` rejects it — proving its
    guard rather than ours. `ride.gpx` is a name storage would happily keep, so the
    assertions below can only pass if `gpx_upload_path` replaced it.
    """
    track = make_gpx_track(trip)

    track.file.save("ride.gpx", ContentFile(b"<gpx/>"), save=True)

    stored_name = track.file.name
    assert stored_name is not None
    assert stored_name.startswith(f"gpx/{trip.owner_id}/{trip.pk}/")
    assert stored_name.endswith(".gpx")
    assert "ride" not in stored_name
    # The row must carry the generated name too, not just the in-memory instance.
    assert GpxTrack.objects.get(pk=track.pk).file.name == stored_name
    with track.file.open("rb") as handle:
        assert handle.read() == b"<gpx/>"


@pytest.mark.django_db
def test_points_and_bounds_survive_a_round_trip_through_the_database(
    trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """Phase 5 renders the map straight from these columns, so their shape has to hold.

    The factory assigns them in memory, where a `points` column that came back as a
    JSON *string* would still satisfy every other test in this file. Only a re-read from
    a fresh query can tell the difference. The bounds are four explicit `FloatField`s
    rather than a nested blob precisely so their types are unambiguous — asserted here
    rather than assumed.
    """
    track = make_gpx_track(trip)

    reloaded = GpxTrack.objects.get(pk=track.pk)

    assert reloaded.points == GPX_POINTS
    assert all(isinstance(value, float) for point in reloaded.points for value in point)
    assert (reloaded.min_latitude, reloaded.min_longitude) == (50.06, 19.94)
    assert (reloaded.max_latitude, reloaded.max_longitude) == (50.07, 19.95)
    assert all(
        isinstance(bound, float)
        for bound in (
            reloaded.min_latitude,
            reloaded.min_longitude,
            reloaded.max_latitude,
            reloaded.max_longitude,
        )
    )
