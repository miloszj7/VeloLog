"""What the trip detail page must deliver for the map to draw — and must not.

The map itself runs in a browser, so these tests cover the server's half of the
contract: the container exists, the coordinates arrive as data rather than as code,
the asset URLs come from the staticfiles storage, and a trip with no route renders
none of it.
"""

import json
import re
from datetime import UTC, date, datetime
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from gpx.constants import STAGE_COLORS
from gpx.models import GpxTrack
from tests.conftest import GPX_BOUNDS, GPX_POINTS, TrackFactory
from trips.models import Trip

MAP_CONFIG_SCRIPT = re.compile(
    r'<script id="map-config" type="application/json">(?P<payload>.*?)</script>', re.DOTALL
)
ANY_SCRIPT_TAG = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL)
MAP_CONTAINER = re.compile(r'<div id="map">(?P<inner>.*?)</div>', re.DOTALL)


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


def make_track(
    trip: Trip,
    filename: str,
    points: list[list[float]],
    bounds: dict[str, float],
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> GpxTrack:
    """Persist a stage with fully custom points/bounds/instants.

    `make_gpx_track` (in `tests/conftest.py`) hardcodes one shared set of points and
    bounds for every caller, which is right for single-stage tests but cannot build the
    distinguishable, orderable stages a multi-stage payload test needs.
    """
    return GpxTrack.objects.create(
        trip=trip,
        file=f"gpx/1/1/{filename}",
        points=points,
        original_filename=filename,
        started_at=started_at,
        ended_at=ended_at,
        **bounds,
    )


@pytest.mark.django_db
def test_a_single_stage_trips_payload_carries_one_segment_matching_its_stored_points(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(trip)

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert '<div id="map">' in body
    payload = map_config_payload(body)
    assert payload["segments"] == [{"number": 1, "color": STAGE_COLORS[0], "points": GPX_POINTS}]
    assert payload["bounds"] == [
        [GPX_BOUNDS["min_latitude"], GPX_BOUNDS["min_longitude"]],
        [GPX_BOUNDS["max_latitude"], GPX_BOUNDS["max_longitude"]],
    ]


@pytest.mark.django_db
def test_a_three_stage_trip_carries_three_segments_in_ride_order_with_distinct_colours(
    auth_client: Client, trip: Trip
) -> None:
    """Uploaded out of ride order, so a passing test proves `started_at` drives the sort."""
    make_track(
        trip,
        "day-3.gpx",
        points=[[50.20, 19.20]],
        bounds={
            "min_latitude": 50.20,
            "min_longitude": 19.20,
            "max_latitude": 50.20,
            "max_longitude": 19.20,
        },
        started_at=datetime(2026, 6, 3, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 3, 9, 0, tzinfo=UTC),
    )
    make_track(
        trip,
        "day-1.gpx",
        points=[[50.00, 19.00]],
        bounds={
            "min_latitude": 50.00,
            "min_longitude": 19.00,
            "max_latitude": 50.00,
            "max_longitude": 19.00,
        },
        started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )
    make_track(
        trip,
        "day-2.gpx",
        points=[[50.10, 19.10]],
        bounds={
            "min_latitude": 50.10,
            "min_longitude": 19.10,
            "max_latitude": 50.10,
            "max_longitude": 19.10,
        },
        started_at=datetime(2026, 6, 2, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
    )

    payload = map_config_payload(auth_client.get(detail_url(trip)).content.decode())

    assert [segment["number"] for segment in payload["segments"]] == [1, 2, 3]
    assert [segment["points"] for segment in payload["segments"]] == [
        [[50.00, 19.00]],
        [[50.10, 19.10]],
        [[50.20, 19.20]],
    ]
    colours = [segment["color"] for segment in payload["segments"]]
    assert colours == list(STAGE_COLORS[:3])
    assert len(set(colours)) == 3


@pytest.mark.django_db
def test_whole_trip_bounds_equal_the_min_max_across_all_stages(
    auth_client: Client, trip: Trip
) -> None:
    make_track(
        trip,
        "south.gpx",
        points=[[50.00, 19.00]],
        bounds={
            "min_latitude": 50.00,
            "min_longitude": 19.00,
            "max_latitude": 50.05,
            "max_longitude": 19.05,
        },
    )
    make_track(
        trip,
        "north.gpx",
        points=[[50.20, 19.20]],
        bounds={
            "min_latitude": 50.15,
            "min_longitude": 19.15,
            "max_latitude": 50.20,
            "max_longitude": 19.20,
        },
    )

    payload = map_config_payload(auth_client.get(detail_url(trip)).content.decode())

    assert payload["bounds"] == [[50.00, 19.00], [50.20, 19.20]]


@pytest.mark.django_db
def test_markers_are_exactly_one_start_one_finish_and_one_break_per_boundary(
    auth_client: Client, trip: Trip
) -> None:
    make_track(
        trip,
        "day-2.gpx",
        points=[[50.10, 19.10], [50.11, 19.11]],
        bounds={
            "min_latitude": 50.10,
            "min_longitude": 19.10,
            "max_latitude": 50.11,
            "max_longitude": 19.11,
        },
        started_at=datetime(2026, 6, 2, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
    )
    make_track(
        trip,
        "day-1.gpx",
        points=[[50.00, 19.00], [50.01, 19.01]],
        bounds={
            "min_latitude": 50.00,
            "min_longitude": 19.00,
            "max_latitude": 50.01,
            "max_longitude": 19.01,
        },
        started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )

    payload = map_config_payload(auth_client.get(detail_url(trip)).content.decode())

    kinds = [marker["kind"] for marker in payload["markers"]]
    assert kinds.count("start") == 1
    assert kinds.count("finish") == 1
    assert kinds.count("break") == 1
    start = next(marker for marker in payload["markers"] if marker["kind"] == "start")
    finish = next(marker for marker in payload["markers"] if marker["kind"] == "finish")
    breakpoint_marker = next(marker for marker in payload["markers"] if marker["kind"] == "break")
    assert start["point"] == [50.00, 19.00]
    assert finish["point"] == [50.11, 19.11]
    assert breakpoint_marker["point"] == [50.01, 19.01]


@pytest.mark.django_db
def test_no_break_markers_when_any_stage_lacks_started_at(auth_client: Client, trip: Trip) -> None:
    make_track(
        trip,
        "timed.gpx",
        points=[[50.00, 19.00]],
        bounds={
            "min_latitude": 50.00,
            "min_longitude": 19.00,
            "max_latitude": 50.00,
            "max_longitude": 19.00,
        },
        started_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        ended_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )
    make_track(
        trip,
        "untimed.gpx",
        points=[[50.10, 19.10]],
        bounds={
            "min_latitude": 50.10,
            "min_longitude": 19.10,
            "max_latitude": 50.10,
            "max_longitude": 19.10,
        },
    )

    payload = map_config_payload(auth_client.get(detail_url(trip)).content.decode())

    assert all(marker["kind"] != "break" for marker in payload["markers"])


@pytest.mark.django_db
def test_a_stage_with_no_points_is_skipped_without_raising_and_the_rest_still_draw(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(trip, original_filename="healthy.gpx")
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
    payload = map_config_payload(body)
    assert len(payload["segments"]) == 1
    assert payload["segments"][0]["points"] == GPX_POINTS


@pytest.mark.django_db
def test_the_map_container_ships_with_a_fallback_message_inside_it(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """An empty container is not an acceptable failure state, so it never ships empty.

    Nothing the server can check covers a client that fails to draw: JavaScript off, a
    Leaflet or stylesheet that 404s, stored points the client chokes on. The NFR that
    forbids a blank page is met by shipping the message *inside* `#map` and having
    `gpx/map.js` remove it on success, so the default outcome is a sentence rather than an
    empty 60vh rectangle.
    """
    make_gpx_track(trip)

    body = auth_client.get(detail_url(trip)).content.decode()

    container = MAP_CONTAINER.search(body)
    assert container is not None, "the page emitted no map container"
    assert "map-fallback" in container.group("inner")
    assert "The map could not be loaded" in container.group("inner")


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

    Moving `STATIC_URL` and requiring the payload to follow is what catches a literal path
    written out in `map_config.py`, which any assertion checking only the filename would
    accept. It proves the prefix was applied and no more: the autouse
    `_plain_staticfiles_storage` fixture builds these URLs by concatenation, so nothing
    here exercises the hashed names production actually serves. That is asserted under the
    real backend in `tests/test_static_references.py`.
    """
    settings.STATIC_URL = "/assets-under-test/"
    make_gpx_track(trip)

    payload = map_config_payload(auth_client.get(detail_url(trip)).content.decode())

    for kind in ("start", "finish", "break"):
        icons = payload["icons"][kind]
        assert icons["iconUrl"] == "/assets-under-test/gpx/vendor/leaflet/images/marker-icon.png"
        assert (
            icons["iconRetinaUrl"]
            == "/assets-under-test/gpx/vendor/leaflet/images/marker-icon-2x.png"
        )
        assert (
            icons["shadowUrl"] == "/assets-under-test/gpx/vendor/leaflet/images/marker-shadow.png"
        )


@pytest.mark.django_db
def test_a_trip_with_no_stages_renders_no_map_container(auth_client: Client, trip: Trip) -> None:
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
    assert map_config_payload(body)["segments"][0]["points"] == GPX_POINTS
    assert "This route could not be displayed" not in body
