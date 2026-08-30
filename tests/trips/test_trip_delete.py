"""Deleting a trip: the confirmation page, the deletion itself, and who may reach either.

The file-removal test wraps its POST in `django_capture_on_commit_callbacks(execute=True)`.
`gpx.signals` schedules the storage delete through `transaction.on_commit`, and
pytest-django wraps each test in a transaction that never commits — without the capture
the callback is silently skipped and the assertion passes while proving nothing.
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import DjangoCaptureOnCommitCallbacks

from gpx.models import GpxTrack
from tests.conftest import StoredTrackFactory
from trips.models import Trip

GPX_WARNING = "Its GPX file will be deleted too."


@pytest.mark.django_db
def test_owner_get_shows_the_confirmation_page_and_deletes_nothing(
    auth_client: Client, rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """A confirmation page that deletes on GET is the failure this asserts against."""
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    make_stored_track(trip)

    response = auth_client.get(reverse("trips:delete", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert "Alps Loop" in body
    assert "This cannot be undone." in body
    assert GPX_WARNING in body
    assert Trip.objects.count() == 1
    assert GpxTrack.objects.count() == 1


@pytest.mark.django_db
def test_confirmation_page_for_a_trackless_trip_omits_the_gpx_warning(
    auth_client: Client, rider: User
) -> None:
    """The only automated check on the `{% if trip.tracks.exists %}` branch.

    Warning a rider they are about to lose a file they never uploaded is the kind of
    wrong-but-harmless copy nothing else in the suite would catch.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.get(reverse("trips:delete", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert "Alps Loop" in body
    assert GPX_WARNING not in body


@pytest.mark.django_db
def test_confirmation_page_cancels_back_to_the_trip(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.get(reverse("trips:delete", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert f'href="{trip.get_absolute_url()}"' in body
    assert ">Cancel<" in body


@pytest.mark.django_db
def test_detail_page_links_to_the_confirmation_page(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    delete_url = reverse("trips:delete", kwargs={"pk": trip.pk})

    response = auth_client.get(trip.get_absolute_url())

    assert f'href="{delete_url}"' in response.content.decode()


@pytest.mark.django_db
def test_owner_post_deletes_the_trip_and_redirects_to_the_list(
    auth_client: Client, rider: User
) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.post(reverse("trips:delete", kwargs={"pk": trip.pk}))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("trips:list")
    assert not Trip.objects.filter(pk=trip.pk).exists()


@pytest.mark.django_db
def test_success_message_renders_on_the_trip_list_after_delete(
    auth_client: Client, rider: User
) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    auth_client.post(reverse("trips:delete", kwargs={"pk": trip.pk}))
    response = auth_client.get(reverse("trips:list"))

    assert "Trip deleted." in response.content.decode()


@pytest.mark.django_db
def test_deleted_trips_detail_url_returns_404(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    detail_url = trip.get_absolute_url()

    auth_client.post(reverse("trips:delete", kwargs={"pk": trip.pk}))
    response = auth_client.get(detail_url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_removes_the_trips_track_rows_and_their_files(
    auth_client: Client,
    rider: User,
    make_stored_track: StoredTrackFactory,
    django_capture_on_commit_callbacks: DjangoCaptureOnCommitCallbacks,
) -> None:
    """The end-to-end proof that the `post_delete` receiver reaches a view-driven cascade.

    Two tracks, because `GpxTrack.trip` is a `ForeignKey` — one-track-per-trip is a rule
    the upload view enforces, not one the schema does, so N tracks is the shape the delete
    path has to survive. This assertion is what the whole S-03 file-cleanup handoff was
    for: without the receiver, the collector fast-deletes these rows and strands both
    files on the Volume forever.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    first = make_stored_track(trip, b"<gpx>1</gpx>", "day-1.gpx")
    second = make_stored_track(trip, b"<gpx>2</gpx>", "day-2.gpx")
    names = [first.file.name, second.file.name]
    assert all(name is not None and default_storage.exists(name) for name in names)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(reverse("trips:delete", kwargs={"pk": trip.pk}))

    assert response.status_code == 302
    assert not Trip.objects.filter(pk=trip.pk).exists()
    assert GpxTrack.objects.count() == 0
    assert not any(name is not None and default_storage.exists(name) for name in names)


@pytest.mark.django_db
def test_another_users_trip_get_returns_404_and_leaks_nothing(
    auth_client: Client, other_rider: User
) -> None:
    other_trip = Trip.objects.create(
        name="Other Rider Trip", date=date(2026, 6, 1), owner=other_rider
    )

    response = auth_client.get(reverse("trips:delete", kwargs={"pk": other_trip.pk}))

    assert response.status_code == 404
    assert "Other Rider Trip" not in response.content.decode()
    assert Trip.objects.filter(pk=other_trip.pk).exists()


@pytest.mark.django_db
def test_another_users_trip_post_returns_404_and_the_trip_survives(
    auth_client: Client, other_rider: User
) -> None:
    """The 404 alone would pass against a view that deleted first and refused afterwards."""
    other_trip = Trip.objects.create(
        name="Other Rider Trip", date=date(2026, 6, 1), owner=other_rider
    )

    response = auth_client.post(reverse("trips:delete", kwargs={"pk": other_trip.pk}))

    assert response.status_code == 404
    assert Trip.objects.filter(pk=other_trip.pk).exists()


@pytest.mark.django_db
def test_unauthenticated_get_redirects_to_login_with_next(client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    delete_url = reverse("trips:delete", kwargs={"pk": trip.pk})

    response = client.get(delete_url)

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={delete_url}"


@pytest.mark.django_db
def test_unauthenticated_post_redirects_to_login_and_deletes_nothing(
    client: Client, rider: User
) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    delete_url = reverse("trips:delete", kwargs={"pk": trip.pk})

    response = client.post(delete_url)

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={delete_url}"
    assert Trip.objects.filter(pk=trip.pk).exists()


@pytest.mark.django_db
def test_put_is_rejected_as_a_disallowed_method(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.put(reverse("trips:delete", kwargs={"pk": trip.pk}))

    assert response.status_code == 405
    assert Trip.objects.filter(pk=trip.pk).exists()


@pytest.mark.django_db
def test_http_delete_is_rejected_and_the_trip_survives(auth_client: Client, rider: User) -> None:
    """Holds only because the view narrows `http_method_names`.

    Left at the default, `DeletionMixin.delete()` stays reachable by name and `dispatch`
    routes a raw HTTP `DELETE` straight to it — `get_object()`, `self.object.delete()`,
    302 — skipping the confirmation page entirely and, through the `post_delete` receiver,
    taking the GPX file with it. The test client sends no CSRF token and needs none, so
    this is reachable in production too. The surviving-trip assertion is the point: a 405
    without it would still pass against a view that deleted and then refused.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.delete(reverse("trips:delete", kwargs={"pk": trip.pk}))

    assert response.status_code == 405
    assert Trip.objects.filter(pk=trip.pk).exists()


@pytest.mark.django_db
def test_head_and_options_are_served_and_delete_nothing(auth_client: Client, rider: User) -> None:
    """The same reason as `test_trip_edit.py`'s pair, plus the verb this page must refuse.

    `head` aliases `get`, which only renders the confirmation page, so the survival
    assertion is what separates "served" from "served and acted". `Allow` naming DELETE
    would mean the narrowing that keeps the Delete link safe to be a link had been dropped.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    url = reverse("trips:delete", kwargs={"pk": trip.pk})

    assert auth_client.head(url).status_code == 200

    options = auth_client.options(url)

    assert options.status_code == 200
    assert "DELETE" not in options.headers["Allow"]
    assert "PUT" not in options.headers["Allow"]
    assert Trip.objects.filter(pk=trip.pk).exists()
