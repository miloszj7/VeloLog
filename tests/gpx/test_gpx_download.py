import pytest
from django.contrib.auth.models import User
from django.http import FileResponse
from django.test import Client
from django.urls import reverse

from gpx.models import GpxTrack
from tests.gpx.conftest import StoredTrackFactory
from trips.models import Trip

TRACK_BYTES = b'<?xml version="1.0"?><gpx version="1.1"><trk/></gpx>'


def download_url(track: GpxTrack) -> str:
    return reverse("gpx:download", kwargs={"pk": track.pk})


@pytest.mark.django_db
def test_the_owner_gets_the_original_bytes_back(
    auth_client: Client, trip: Trip, make_stored_track: StoredTrackFactory
) -> None:
    track = make_stored_track(trip, TRACK_BYTES)

    response = auth_client.get(download_url(track))

    assert response.status_code == 200
    # The response streams the file rather than buffering it, so `.content` does not
    # apply — and the `isinstance` is what tells the type checker that.
    assert isinstance(response, FileResponse)
    assert b"".join(response.streaming_content) == TRACK_BYTES


@pytest.mark.django_db
def test_the_download_is_an_attachment_named_by_the_users_own_filename(
    auth_client: Client, trip: Trip, make_stored_track: StoredTrackFactory
) -> None:
    """The stored name is random by design, so the user's name has to be restored here.

    `gpx_upload_path` deliberately discards the uploaded filename — the only copy left is
    the `original_filename` column, and this header is the only place it reaches the user
    again.
    """
    track = make_stored_track(trip, TRACK_BYTES, "pyrenees-stage-3.gpx")

    response = auth_client.get(download_url(track))
    disposition = response.headers["Content-Disposition"]

    assert disposition.startswith("attachment;")
    assert "pyrenees-stage-3.gpx" in disposition


@pytest.mark.django_db
def test_another_users_track_returns_404_not_403(
    auth_client: Client, other_rider: User, make_stored_track: StoredTrackFactory
) -> None:
    other_trip = Trip.objects.create(name="Other Rider Trip", date="2026-06-01", owner=other_rider)
    other_track = make_stored_track(other_trip, b"someone-elses-ride")

    response = auth_client.get(download_url(other_track))

    assert response.status_code == 404


@pytest.mark.django_db
def test_an_unauthenticated_request_redirects_to_login(
    client: Client, trip: Trip, make_stored_track: StoredTrackFactory
) -> None:
    """A `MEDIA_URL` path would serve these bytes to anyone with the link.

    whitenoise sits ahead of `AuthenticationMiddleware` in `MIDDLEWARE`, so anything it
    serves is outside authorization by construction — which is why this route exists at
    all rather than a link straight at the file.
    """
    track = make_stored_track(trip, TRACK_BYTES)
    url = download_url(track)

    response = client.get(url)

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={url}"
