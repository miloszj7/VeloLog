import pytest
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import DjangoCaptureOnCommitCallbacks

from gpx.constants import MAX_GPX_FILE_BYTES
from gpx.models import GpxTrack
from tests.gpx.conftest import GpxBytesReader
from trips.models import Trip

VALID_POINTS = [[50.06, 19.94], [50.07, 19.95], [50.05, 19.96]]


def upload_url(trip: Trip) -> str:
    return reverse("gpx:upload", kwargs={"pk": trip.pk})


def stored_name(track: GpxTrack) -> str:
    """Return a track's storage key, narrowing away `FieldFile.name`'s optional.

    A `None` here would mean the file never reached storage at all, so asserting it is
    the assertion the caller wanted anyway.
    """
    name = track.file.name
    assert name is not None
    return name


@pytest.mark.django_db
def test_a_valid_upload_persists_the_exact_bytes_that_were_submitted(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    """The byte-for-byte comparison is the point of this test, not the redirect.

    `clean_file` reads the whole upload to parse it, which leaves the cursor at EOF; a
    missing rewind before the storage write persists an empty file. Every status-code
    assertion in this module still passes in that state — only reading the stored bytes
    back catches it.
    """
    content = gpx_bytes("valid-track.gpx")

    response = auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("alps-day-1.gpx", content, content_type="application/gpx+xml")},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == trip.get_absolute_url()
    track = GpxTrack.objects.get()
    assert track.trip == trip
    assert track.original_filename == "alps-day-1.gpx"
    with track.file.open("rb") as handle:
        assert handle.read() == content


@pytest.mark.django_db
def test_a_valid_upload_stores_the_points_and_bounds_parsed_from_it(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    """Parsing happens once, at upload — so the columns the map reads must be filled here.

    Re-read from the database rather than asserted on the in-memory instance: `points`
    is a `JSONField`, and a value that only looks right before it round-trips is exactly
    the failure Phase 5 would inherit.
    """
    auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("alps-day-1.gpx", gpx_bytes("valid-track.gpx"))},
    )

    track = GpxTrack.objects.get()

    assert track.points == VALID_POINTS
    assert (track.min_latitude, track.max_latitude) == (50.05, 50.07)
    assert (track.min_longitude, track.max_longitude) == (19.94, 19.96)


@pytest.mark.django_db
def test_a_valid_upload_returns_to_the_detail_page_with_a_confirmation(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    response = auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("alps-day-1.gpx", gpx_bytes("valid-track.gpx"))},
        follow=True,
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "Route uploaded." in body
    assert "alps-day-1.gpx" in body
    assert "No route yet" not in body


@pytest.mark.django_db
def test_a_file_over_the_size_cap_is_rejected_with_a_visible_message(
    auth_client: Client, trip: Trip
) -> None:
    oversized = SimpleUploadedFile("huge.gpx", b"x" * (MAX_GPX_FILE_BYTES + 1))

    response = auth_client.post(upload_url(trip), {"file": oversized})

    assert response.status_code == 200
    assert "larger than 10 MB" in response.content.decode()
    assert GpxTrack.objects.count() == 0


@pytest.mark.django_db
def test_a_non_gpx_extension_is_rejected_with_a_visible_message(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    """The contents are a perfectly good track — only the extension is wrong.

    Using valid GPX bytes here is deliberate: it proves the extension check runs and
    rejects on its own, rather than the file happening to fail the parse a moment later.
    """
    disguised = SimpleUploadedFile("alps-day-1.txt", gpx_bytes("valid-track.gpx"))

    response = auth_client.post(upload_url(trip), {"file": disguised})

    assert response.status_code == 200
    assert "not a .gpx file" in response.content.decode()
    assert GpxTrack.objects.count() == 0


@pytest.mark.django_db
def test_an_uppercase_gpx_extension_is_accepted(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    response = auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("ALPS-DAY-1.GPX", gpx_bytes("valid-track.gpx"))},
    )

    assert response.status_code == 302
    assert GpxTrack.objects.count() == 1


@pytest.mark.django_db
def test_malformed_xml_is_rejected_with_the_error_shown_on_the_page(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    """Assert the message, not just the 200 — a blank re-rendered form is also a 200."""
    response = auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("broken.gpx", gpx_bytes("malformed.gpx"))},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "could not be read as XML" in body
    assert "No route yet" in body
    assert GpxTrack.objects.count() == 0


@pytest.mark.django_db
def test_a_valid_xml_file_that_is_not_a_track_is_rejected_with_its_own_message(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    """Not-XML and not-GPX are two different failures and get two different messages."""
    response = auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("shopping.gpx", gpx_bytes("not-gpx.gpx"))},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "not a usable GPX track" in body
    assert GpxTrack.objects.count() == 0


@pytest.mark.django_db
def test_a_rejected_upload_leaves_an_existing_track_untouched(
    auth_client: Client, trip: Trip, gpx_bytes: GpxBytesReader
) -> None:
    auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("alps-day-1.gpx", gpx_bytes("valid-track.gpx"))},
    )
    existing = GpxTrack.objects.get()

    response = auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("broken.gpx", gpx_bytes("malformed.gpx"))},
    )

    assert response.status_code == 200
    assert list(GpxTrack.objects.all()) == [existing]
    assert default_storage.exists(stored_name(existing))


@pytest.mark.django_db
def test_a_second_upload_replaces_the_first_and_removes_its_file(
    auth_client: Client,
    trip: Trip,
    gpx_bytes: GpxBytesReader,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """One track per trip, and no orphan left on the volume.

    The superseded file is deleted through `transaction.on_commit`, and pytest-django
    wraps each test in a transaction that never commits — so without
    `django_capture_on_commit_callbacks(execute=True)` the deferred delete is silently
    skipped and this test passes while proving nothing about it.
    """
    auth_client.post(
        upload_url(trip),
        {"file": SimpleUploadedFile("first.gpx", gpx_bytes("valid-track.gpx"))},
    )
    first = GpxTrack.objects.get()
    first_file_name = stored_name(first)
    assert default_storage.exists(first_file_name)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(
            upload_url(trip),
            {"file": SimpleUploadedFile("second.gpx", gpx_bytes("second-track.gpx"))},
        )

    assert response.status_code == 302
    replacement = GpxTrack.objects.get()
    assert replacement.pk != first.pk
    assert replacement.original_filename == "second.gpx"
    assert replacement.points == [[49.30, 19.95], [49.29, 19.93]]
    assert default_storage.exists(stored_name(replacement))
    assert not default_storage.exists(first_file_name)


@pytest.mark.django_db
def test_a_second_upload_leaves_another_trips_track_alone(
    auth_client: Client,
    rider: User,
    trip: Trip,
    gpx_bytes: GpxBytesReader,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The replace is scoped to the trip being uploaded to, not to the rider's tracks.

    An unscoped "delete the other tracks" would pass every assertion in the test above
    and quietly destroy the rest of the rider's trips.
    """
    other_trip = Trip.objects.create(name="Pyrenees Loop", date="2026-07-01", owner=rider)
    auth_client.post(
        upload_url(other_trip),
        {"file": SimpleUploadedFile("pyrenees.gpx", gpx_bytes("second-track.gpx"))},
    )
    untouched = GpxTrack.objects.get(trip=other_trip)

    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(
            upload_url(trip),
            {"file": SimpleUploadedFile("alps.gpx", gpx_bytes("valid-track.gpx"))},
        )

    assert GpxTrack.objects.filter(pk=untouched.pk).exists()
    assert default_storage.exists(stored_name(untouched))
    assert GpxTrack.objects.filter(trip=trip).count() == 1


@pytest.mark.django_db
def test_uploading_to_another_users_trip_returns_404_and_creates_nothing(
    auth_client: Client, other_rider: User, gpx_bytes: GpxBytesReader
) -> None:
    other_trip = Trip.objects.create(name="Other Rider Trip", date="2026-06-01", owner=other_rider)

    response = auth_client.post(
        upload_url(other_trip),
        {"file": SimpleUploadedFile("alps-day-1.gpx", gpx_bytes("valid-track.gpx"))},
    )

    assert response.status_code == 404
    assert GpxTrack.objects.count() == 0


@pytest.mark.django_db
def test_an_unauthenticated_post_redirects_to_login_and_creates_nothing(
    client: Client, rider: User, gpx_bytes: GpxBytesReader
) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)
    url = upload_url(trip)

    response = client.post(
        url, {"file": SimpleUploadedFile("alps-day-1.gpx", gpx_bytes("valid-track.gpx"))}
    )

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={url}"
    assert GpxTrack.objects.count() == 0


@pytest.mark.django_db
def test_the_upload_url_does_not_serve_a_page_of_its_own(auth_client: Client, trip: Trip) -> None:
    """The form lives on the trip detail page; this URL is only its target.

    A GET that rendered `trip_detail.html` would put a second, unlinked copy of the page
    at an address nothing links to and `get_absolute_url` does not know about.
    """
    response = auth_client.get(upload_url(trip))

    assert response.status_code == 405
