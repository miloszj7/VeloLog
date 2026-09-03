from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse
from django.utils.formats import date_format

from tests.conftest import StoredTrackFactory, TrackFactory
from trips.models import Trip


@pytest.mark.django_db
def test_owner_sees_own_trip_detail(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(
        name="Alps Loop",
        date=date(2026, 6, 1),
        description="A week in the mountains.",
        owner=rider,
    )

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["trip"] == trip
    assert "Alps Loop" in body
    assert date_format(trip.date) in body
    assert "A week in the mountains." in body


@pytest.mark.django_db
def test_another_users_trip_returns_404_not_403(
    auth_client: Client, rider: User, other_rider: User
) -> None:
    other_trip = Trip.objects.create(name="Other Rider Trip", date="2026-06-01", owner=other_rider)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": other_trip.pk}))

    assert response.status_code == 404
    assert "Other Rider Trip" not in response.content.decode()


@pytest.mark.django_db
def test_unauthenticated_get_redirects_to_login_with_next(client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    detail_url = reverse("trips:detail", kwargs={"pk": trip.pk})

    response = client.get(detail_url)

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={detail_url}"


@pytest.mark.django_db
def test_trip_with_no_track_renders_the_empty_state_copy(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))

    assert response.status_code == 200
    assert response.context["stages"] == ()
    assert "No route yet" in response.content.decode()


@pytest.mark.django_db
def test_trip_with_a_track_renders_only_its_own_track(
    auth_client: Client, rider: User, make_gpx_track: TrackFactory
) -> None:
    """A second, newer track on another of the rider's trips must not leak onto this page.

    `GpxTrack.Meta.ordering` is newest-first, so an unscoped `GpxTrack.objects.first()`
    would return the Pyrenees track here — that is the wrong implementation this test
    exists to reject.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    track = make_gpx_track(trip, "alps-loop.gpx")
    other_trip = Trip.objects.create(name="Pyrenees Loop", date=date(2026, 7, 1), owner=rider)
    make_gpx_track(other_trip, "pyrenees-loop.gpx")

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert [stage.track for stage in response.context["stages"]] == [track]
    assert "alps-loop.gpx" in body
    assert "pyrenees-loop.gpx" not in body
    assert "No route yet" not in body


@pytest.mark.django_db
def test_a_rider_sees_a_live_download_link_when_the_track_file_is_present(
    auth_client: Client, rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """The healthy-state companion to the storage-miss test below.

    Both branches of a stage's `file_available` need their own assertion — proving the
    marker renders when the file is gone says nothing about whether it wrongly renders
    when the file is fine.
    """
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    track = make_stored_track(trip)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stages"][0].file_available is True
    assert f'href="{reverse("gpx:download", kwargs={"pk": track.pk})}"' in body
    assert "Track file unavailable" not in body


@pytest.mark.django_db
def test_a_rider_sees_a_deliberate_marker_when_the_track_file_is_missing(
    auth_client: Client, rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """Risk #3's actual claim: stats present + file gone must not render as healthy.

    The file is removed via `default_storage.delete(name)` rather than `track.delete()`
    — the latter would remove the row too, and this test needs the row to survive with
    the file simply gone from underneath it.
    """
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    track = make_stored_track(trip)
    name = track.file.name
    assert name is not None
    default_storage.delete(name)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stages"][0].file_available is False
    assert "Track file unavailable" in body
    assert f'href="{reverse("gpx:download", kwargs={"pk": track.pk})}"' not in body


@pytest.mark.django_db
def test_a_missing_file_and_unbackfilled_stats_both_render_together(
    auth_client: Client, rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """The one combination the isolated file and stats tests do not exercise together.

    `make_stored_track` leaves stats null by not setting them, so combining it with the
    same `default_storage.delete(name)` step the file-missing test above performs gives a
    track that is simultaneously degraded on both dimensions — proving neither template
    branch suppresses or corrupts the other.
    """
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    track = make_stored_track(trip)
    name = track.file.name
    assert name is not None
    default_storage.delete(name)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert "Track file unavailable" in body
    assert "These stats have not been worked out for this route." in body


@pytest.mark.django_db
def test_a_missing_stage_file_renders_unavailable_while_siblings_keep_live_links(
    auth_client: Client, rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """One stage's missing file must not degrade its siblings' download links.

    `build_stages` resolves `file_available` per stage — a bug that leaked one stage's
    missing-file state onto the whole trip would pass every single-stage file-availability
    test above and only show up once a trip actually has more than one stage.
    """
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    healthy = make_stored_track(trip, b"<gpx>1</gpx>", "day-1.gpx")
    missing = make_stored_track(trip, b"<gpx>2</gpx>", "day-2.gpx")
    name = missing.file.name
    assert name is not None
    default_storage.delete(name)

    response = auth_client.get(reverse("trips:detail", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    stages = {stage.track.pk: stage for stage in response.context["stages"]}
    assert stages[healthy.pk].file_available is True
    assert stages[missing.pk].file_available is False
    assert f'href="{reverse("gpx:download", kwargs={"pk": healthy.pk})}"' in body
    assert "Track file unavailable" in body
