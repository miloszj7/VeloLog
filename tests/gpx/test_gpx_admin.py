"""The admin change form for `GpxTrack` — the path that actually stranded files.

This is the suite's first admin request. `GpxTrackAdmin` excludes only `points`, so `file`
renders as an editable upload widget on what its own docstring calls the read/repair path;
a replacement there `UPDATE`s the row rather than deleting it, which is why `post_delete`
never saw it and why `pre_save` had to. Proving the receiver at model level is not enough
on its own — the form is what decides which fields reach `save_form_data` at all, so a
change to `exclude` or `readonly_fields` could re-open the strand with every signal test
still green.

`admin_client` and `admin_user` ship with pytest-django; no conftest fixture is needed.
"""

from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import DjangoCaptureOnCommitCallbacks

from gpx.models import GpxTrack
from tests.conftest import StoredTrackFactory
from trips.models import Trip


@pytest.fixture
def admin_trip(admin_user: User) -> Trip:
    """A trip owned by the superuser the admin client authenticates as.

    Ownership is irrelevant to the admin — it has no per-object scoping — but keeping the
    row consistent means the trip detail page can be reached afterwards without a second
    login, and it keeps the fixture honest about who the data belongs to.
    """
    return Trip.objects.create(name="Admin Loop", date="2026-06-01", owner=admin_user)


def change_form_payload(track: GpxTrack, upload: object) -> dict[str, object]:
    """Build a complete POST body for the `GpxTrack` change form.

    Every field the form renders has to be present or Django re-renders the form with
    errors and the row is never saved — which would make the assertions below pass for
    entirely the wrong reason. `points` is excluded from the form and `uploaded_at` is
    readonly, so what remains is the FK, the file, the four bounds and the filename; the
    four statistics are `blank=True` and may be omitted.
    """
    return {
        "trip": str(track.trip_id),
        "file": upload,
        "min_latitude": str(track.min_latitude),
        "min_longitude": str(track.min_longitude),
        "max_latitude": str(track.max_latitude),
        "max_longitude": str(track.max_longitude),
        "original_filename": track.original_filename,
    }


@pytest.mark.django_db
def test_admin_change_form_replacement_reclaims_the_predecessor(
    admin_client: Client,
    admin_trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
    tmp_path: Path,
) -> None:
    """A staff repair leaves exactly one file behind, not two.

    The directory count is the assertion that would still have caught this if the key
    comparison had been written the other way round: before the receiver existed, both
    files sat here and only the newer one was reachable from any row.
    """
    track = make_stored_track(admin_trip)
    predecessor = track.file.name
    assert predecessor is not None
    assert default_storage.exists(predecessor)

    url = reverse("admin:gpx_gpxtrack_change", args=[track.pk])
    with (tmp_path / "replacement.gpx").open("wb") as handle:
        handle.write(b"<gpx>replacement</gpx>")

    with django_capture_on_commit_callbacks(execute=True):
        with (tmp_path / "replacement.gpx").open("rb") as upload:
            response = admin_client.post(url, change_form_payload(track, upload))

    assert response.status_code == 302
    track.refresh_from_db()
    successor = track.file.name
    assert successor is not None
    assert successor != predecessor
    assert default_storage.exists(successor)
    assert not default_storage.exists(predecessor)

    directories, files = default_storage.listdir(f"gpx/{admin_trip.owner_id}/{admin_trip.pk}")
    assert directories == []
    assert len(files) == 1


@pytest.mark.django_db
def test_admin_change_form_saved_without_a_new_file_keeps_the_stored_one(
    admin_client: Client,
    admin_trip: Trip,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """Editing any other field through the same form must not reclaim the file.

    This is the case the receiver's key comparison exists for, exercised through the form
    rather than through `Model.save()`: `forms.FileField.clean` hands back the committed
    `FieldFile` when the widget was left alone, so the two keys match and nothing is
    scheduled. A receiver that treated every update as a replacement would destroy the
    track on an ordinary metadata edit.
    """
    track = make_stored_track(admin_trip)
    name = track.file.name
    assert name is not None

    payload = change_form_payload(track, upload="")
    payload["original_filename"] = "renamed-by-staff.gpx"
    del payload["file"]

    url = reverse("admin:gpx_gpxtrack_change", args=[track.pk])
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = admin_client.post(url, payload)

    assert response.status_code == 302
    assert callbacks == []
    track.refresh_from_db()
    assert track.original_filename == "renamed-by-staff.gpx"
    assert track.file.name == name
    assert default_storage.exists(name)
