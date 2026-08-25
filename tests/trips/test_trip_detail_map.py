"""What the trip detail page must deliver for the map to draw — and must not.

The map itself runs in a browser, so these tests cover the server's half of the
contract: the container exists, the coordinates arrive as data rather than as code,
the asset URLs come from the staticfiles storage, and a trip with no route renders
none of it.
"""

import json
import re
from datetime import date
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from gpx.models import GpxTrack
from tests.conftest import GPX_BOUNDS, GPX_POINTS, TrackFactory
from trips.models import Trip

MAP_CONFIG_SCRIPT = re.compile(
    r'<script id="map-config" type="application/json">(?P<payload>.*?)</script>', re.DOTALL
)
ANY_SCRIPT_TAG = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL)


def detail_url(trip: Trip) -> str:
    return reverse("trips:detail", kwargs={"pk": trip.pk})


def map_config_payload(body: str) -> dict[str, Any]:
    """Return the parsed `json_script` blob, failing if the page did not emit one."""
    match = MAP_CONFIG_SCRIPT.search(body)
    assert match is not None, "the page emitted no map-config json_script element"
    parsed = json.loads(match.group("payload"))
    assert isinstance(parsed, dict)
    return parsed


@pytest.fixture
def trip(rider: User) -> Trip:
    return Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)


@pytest.mark.django_db
def test_a_trip_with_a_track_renders_the_map_container_and_its_coordinates(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(trip)

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert '<div id="map">' in body
    payload = map_config_payload(body)
    assert payload["points"] == GPX_POINTS
    assert payload["bounds"] == [
        [GPX_BOUNDS["min_latitude"], GPX_BOUNDS["min_longitude"]],
        [GPX_BOUNDS["max_latitude"], GPX_BOUNDS["max_longitude"]],
    ]


@pytest.mark.django_db
def test_the_map_page_loads_leaflet_and_the_map_script(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """Both the stylesheet and both scripts, or the container renders as an empty box."""
    make_gpx_track(trip)

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "gpx/vendor/leaflet/leaflet.css" in body
    assert "gpx/vendor/leaflet/leaflet.js" in body
    assert "gpx/map.js" in body


@pytest.mark.django_db
def test_the_coordinates_are_delivered_as_data_never_interpolated_into_a_script(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The payload is user-derived, so it must never reach an executable position.

    Asserting the absence of `|safe` in one template would only pin today's template.
    This asserts the property that matters instead: every `<script>` on the rendered
    page either loads a file by `src` or is inert `application/json` data. An inline
    script carrying the coordinates fails it however it was written.
    """
    make_gpx_track(trip)

    body = auth_client.get(detail_url(trip)).content.decode()

    scripts = list(ANY_SCRIPT_TAG.finditer(body))
    assert scripts, "the page rendered no script tags at all — the map cannot draw"
    for script in scripts:
        attrs = script.group("attrs")
        is_external = "src=" in attrs
        is_json_data = 'type="application/json"' in attrs
        assert is_external or is_json_data, (
            f"inline script on the trip detail page: <script{attrs}>"
            f"{script.group('body')[:120]}"
        )
        if is_external:
            assert script.group("body").strip() == ""


@pytest.mark.django_db
def test_the_marker_icon_urls_come_from_the_staticfiles_storage(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory, settings: Settings
) -> None:
    """Hardcoded `/static/...` strings would 404 under the hashed manifest in production.

    Moving `STATIC_URL` and requiring the payload to follow is what distinguishes a URL
    that was resolved from one that was written out — a literal path passes any
    assertion that only checks the filename.
    """
    settings.STATIC_URL = "/assets-under-test/"
    make_gpx_track(trip)

    payload = map_config_payload(auth_client.get(detail_url(trip)).content.decode())

    icons = payload["icons"]
    assert icons["iconUrl"] == "/assets-under-test/gpx/vendor/leaflet/images/marker-icon.png"
    assert (
        icons["iconRetinaUrl"] == "/assets-under-test/gpx/vendor/leaflet/images/marker-icon-2x.png"
    )
    assert icons["shadowUrl"] == "/assets-under-test/gpx/vendor/leaflet/images/marker-shadow.png"


@pytest.mark.django_db
def test_a_trip_with_no_track_renders_no_map_container(auth_client: Client, trip: Trip) -> None:
    """No container, no payload, and no Leaflet — an empty map frame is not an empty state."""
    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["map_config"] is None
    assert 'id="map"' not in body
    assert "map-config" not in body
    assert "leaflet" not in body.lower()
    assert "No route yet" in body


@pytest.mark.django_db
def test_a_stored_track_with_no_points_says_so_instead_of_rendering_an_empty_map(
    auth_client: Client, trip: Trip
) -> None:
    """Unreachable through upload, and deliberate anyway: the NFR forbids a blank page.

    `parse_gpx` rejects a pointless track at the upload boundary, so this row can only
    arrive through the admin or a hand-written migration. It still must not render a map
    container Leaflet would draw nothing into.
    """
    GpxTrack.objects.create(
        trip=trip,
        file="gpx/1/1/deadbeef.gpx",
        points=[],
        original_filename="empty.gpx",
        **GPX_BOUNDS,
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["map_config"] is None
    assert 'id="map"' not in body
    assert "This route could not be displayed" in body
    # The file is still the user's — the failure to draw it must not hide the way out.
    assert "empty.gpx" in body


@pytest.mark.django_db
def test_a_rejected_upload_re_renders_the_route_the_trip_already_had(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The upload view renders this same template, so it owes it the same context.

    Two views render `trips/trip_detail.html`: `TripDetailView` on a visit, and
    `GpxUploadView` when an upload fails validation. If only the first supplies the map
    blob, a rider who picks the wrong file loses the map they already had and is told
    their route could not be displayed — a false failure report about an intact track.
    """
    make_gpx_track(trip)

    response = auth_client.post(
        reverse("gpx:upload", kwargs={"pk": trip.pk}),
        {"file": SimpleUploadedFile("notes.txt", b"not a gpx file", content_type="text/plain")},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert '<div id="map">' in body
    assert map_config_payload(body)["points"] == GPX_POINTS
    assert "This route could not be displayed" not in body
