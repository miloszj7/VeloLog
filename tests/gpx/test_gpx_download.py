from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.http import FileResponse
from django.test import Client
from django.urls import reverse

from gpx.models import GpxTrack
from tests.conftest import StoredTrackFactory
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
def test_a_hostile_original_filename_cannot_break_out_of_the_header(
    auth_client: Client, trip: Trip, make_stored_track: StoredTrackFactory
) -> None:
    """The one place a user-supplied string is written into a response header.

    The guarantee is Django's, not this app's: content_disposition_header escapes
    quotes and falls back to RFC 5987 encoding for anything outside quotable ASCII.
    Pinning it here means a future hand-rolled header, or a Django change, fails a
    test rather than shipping a header-injection hole.
    """
    hostile = chr(34) + "; evil=1" + chr(13) + chr(10) + "X-Injected: yes"
    track = make_stored_track(trip, TRACK_BYTES, hostile + ".gpx")

    response = auth_client.get(download_url(track))
    disposition = response.headers["Content-Disposition"]

    assert response.status_code == 200
    assert "X-Injected" not in response.headers
    assert chr(13) not in disposition
    assert chr(10) not in disposition


@pytest.mark.django_db
def test_another_users_track_returns_404_not_403(
    auth_client: Client, other_rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """404 rather than 403, and none of the other rider's bytes in the answer.

    The status code alone would still pass if the view rendered the foreign file into
    an error page, which is the failure this pair of assertions exists to catch.
    """
    other_trip = Trip.objects.create(name="Other Rider Trip", date="2026-06-01", owner=other_rider)
    other_track = make_stored_track(other_trip, b"someone-elses-ride")

    response = auth_client.get(download_url(other_track))

    assert response.status_code == 404
    assert b"someone-elses-ride" not in response.content
    assert other_track.original_filename not in response.content.decode()


@pytest.mark.django_db
def test_a_row_whose_file_is_gone_returns_404_not_500(
    auth_client: Client, trip: Trip, make_stored_track: StoredTrackFactory
) -> None:
    """The state `DEPLOY.md` warns about: a database restored ahead of its media.

    An unhandled `FileNotFoundError` here is a 500 with nothing in the log to say which
    track was involved. 404 is the same answer this view already gives for a track that
    does not exist, which is what the requester can act on; the operator gets the log
    line instead.
    """
    track = make_stored_track(trip, TRACK_BYTES)
    assert track.file.name is not None
    stored_name = track.file.name
    Path(track.file.path).unlink()

    response = auth_client.get(download_url(track))

    assert response.status_code == 404
    assert stored_name not in response.content.decode()
    assert track.original_filename not in response.content.decode()
    assert GpxTrack.objects.filter(pk=track.pk).exists()


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
