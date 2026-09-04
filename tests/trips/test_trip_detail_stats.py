"""What the trip detail page says about a route's distance, time and elevation.

The formatting itself is pinned in `tests/gpx/test_gpx_statistics.py`; these tests cover
the page's half of the contract — that the section appears where a track does, that a stat
the file never carried reads as a sentence rather than as a zero, that a row whose columns
were never computed says so in its own words, and that both views rendering this template
supply the blob.
"""

import re
from datetime import UTC, date, datetime

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gpx.models import GpxTrack
from tests.conftest import GPX_BOUNDS, GPX_POINTS, StoredTrackFactory, TrackFactory
from trips.models import Trip

# Tolerant of an added class on <h2> (e.g. Bootstrap styling) — still distinguishes the
# heading's presence from its absence, which is what the call sites below need. Points at
# "Stages" rather than "Stats" — Phase 4 folded the old Stats block into the per-stage
# Stages section, and there is no longer a bare "Stats" heading to pin.
STAGES_HEADING = re.compile(r"<h2[^>]*>Stages</h2>")
# Tolerant of an added class on <dd> — a bare "<dd>0 min</dd>" substring check would be
# made vacuously true by any class attribute, silently deleting the zero-vs-null guard.
ZERO_MINUTES_DD = re.compile(r"<dd[^>]*>0 min</dd>")
ZERO_METERS_DD = re.compile(r"<dd[^>]*>0 m</dd>")
# Queries a detail render costs, at *any* stage count: the session, the user, the trip,
# and one query for the trip's tracks. The four statistics are columns on those rows, so
# they add nothing — which is the whole reason they are stored instead of re-parsed. Raise
# this deliberately when the page really does gain a query; a count that scales with the
# number of stages means the tracks' columns went deferred and are being refreshed one
# row at a time.
DETAIL_PAGE_QUERIES = 4

RE_UPLOAD_SENTENCE = "These stats have not been worked out for this route."
NO_TIMESTAMPS_NOTE = "Not recorded — the GPX file carried no usable timestamps."
NO_ELEVATION_NOTE = "Not recorded — the GPX file carried no usable elevation data."
NOT_EVERY_STAGE_NOTE = "Not recorded — not every stage has this figure."
TRIP_TOTALS_HEADING = re.compile(r"<h2[^>]*>Trip totals</h2>")


def detail_url(trip: Trip) -> str:
    return reverse("trips:detail", kwargs={"pk": trip.pk})


@pytest.fixture
def trip(rider: User) -> Trip:
    return Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)


@pytest.mark.django_db
def test_a_track_with_every_statistic_renders_all_four_values(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(
        trip,
        distance_meters=42195.0,
        duration_seconds=8100.0,
        elevation_gain_meters=1240.4,
        elevation_loss_meters=1187.6,
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert STAGES_HEADING.search(body)
    assert "42.2 km" in body
    assert "2 h 15 min" in body
    assert "1240 m" in body
    assert "1188 m" in body
    assert RE_UPLOAD_SENTENCE not in body


@pytest.mark.django_db
def test_the_time_stat_is_labelled_recorded_time_not_elapsed_time(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The label is the semantic, so it is asserted rather than left to the template.

    `duration_seconds` is the sum of each GPX segment's own span — the overnight gaps on a
    multi-day tour are not in it. Calling the number "elapsed" would be wrong by days on
    exactly the kind of trip this product is for.
    """
    make_gpx_track(trip, duration_seconds=8100.0)

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "Recorded time" in body
    assert "Elapsed" not in body


@pytest.mark.django_db
def test_a_track_with_no_timestamps_says_so_and_still_renders_its_distance(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """`valid-track.gpx`'s shape. One absent input may not cost the stats that are present.

    The note, not a zero: "0 min" would read as a ride that took no time rather than as a
    file that never said.
    """
    make_gpx_track(
        trip,
        distance_meters=3661.09,
        elevation_gain_meters=120.0,
        elevation_loss_meters=80.0,
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert "3.7 km" in body
    assert "120 m" in body
    assert NO_TIMESTAMPS_NOTE in body
    assert ZERO_MINUTES_DD.search(body) is None
    assert RE_UPLOAD_SENTENCE not in body


@pytest.mark.django_db
def test_a_track_with_no_elevation_says_so_for_both_elevation_stats(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """`second-track.gpx`'s shape, where only distance survives the parse."""
    make_gpx_track(trip, distance_meters=3661.09)

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "3.7 km" in body
    assert body.count(NO_ELEVATION_NOTE) == 2
    assert NO_TIMESTAMPS_NOTE in body
    assert ZERO_METERS_DD.search(body) is None


@pytest.mark.django_db
def test_a_track_whose_statistics_were_never_computed_points_at_re_upload(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The legacy row: every column null, so the page owes a different sentence.

    Not the per-stat notes — those blame the file, and this row's file may well carry
    everything. What is missing is the computation, and re-uploading is the fix.
    """
    make_gpx_track(trip)

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stages"][0].stats is None
    assert STAGES_HEADING.search(body)
    assert RE_UPLOAD_SENTENCE in body
    assert NO_TIMESTAMPS_NOTE not in body
    assert NO_ELEVATION_NOTE not in body


@pytest.mark.django_db
def test_a_trip_with_no_track_renders_no_stats_section_at_all(
    auth_client: Client, trip: Trip
) -> None:
    """No track, no statistics — and no heading either, exactly as there is no map.

    The section lives inside the template's `{% if stages %}` branch precisely so this
    needs no second condition that could drift out of step with the map's.
    """
    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stages"] == ()
    assert STAGES_HEADING.search(body) is None
    assert RE_UPLOAD_SENTENCE not in body
    assert "Recorded time" not in body


@pytest.mark.django_db
def test_a_rejected_upload_re_renders_the_stats_the_trip_already_had(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The parity both view docstrings warn about, asserted rather than commented.

    `GpxUploadView` renders this same template on a validation error, so it owes it the
    same `stages`. Supplied on the GET path alone, a rider who picks the wrong file is
    told their route's figures were never worked out — a false report about intact data.
    The two responses are compared to each other, so the assertion cannot pass by both
    paths being equally wrong about the values.
    """
    make_gpx_track(
        trip,
        distance_meters=42195.0,
        duration_seconds=8100.0,
        elevation_gain_meters=1240.4,
        elevation_loss_meters=1187.6,
    )
    expected = auth_client.get(detail_url(trip)).context["stages"][0].stats

    response = auth_client.post(
        reverse("gpx:upload", kwargs={"pk": trip.pk}),
        {"file": SimpleUploadedFile("notes.txt", b"not a gpx file", content_type="text/plain")},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["stages"][0].stats == expected
    assert "42.2 km" in body
    assert "2 h 15 min" in body
    assert RE_UPLOAD_SENTENCE not in body


@pytest.mark.django_db
def test_a_stored_zero_renders_as_a_value_and_not_as_the_missing_note(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The other half of the zero-versus-null contract, asserted at the template.

    `build_trip_stats` distinguishes a null column from a legitimate zero, and the page has
    to preserve that distinction rather than re-collapse it. A one-point *timed* file
    genuinely stores `duration_seconds = 0.0`, so the falsy value here is reachable from a
    real upload and not a contrived one.

    Note what this does and does not pin. It passes under a truthiness gate too, because
    every zero formats to a non-empty string — that accident is precisely why the gate read
    as safe. What it pins is that invariant: if a formatter is ever changed to return `""`
    for a zero, this test fails, and the `is not None` gates in the template are what stop
    that change from silently relabelling a real zero as "Not recorded".
    """
    make_gpx_track(
        trip,
        distance_meters=0.0,
        duration_seconds=0.0,
        elevation_gain_meters=0.0,
        elevation_loss_meters=0.0,
    )

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "0.0 km" in body
    assert "0 min" in body
    assert "0 m" in body
    assert NO_TIMESTAMPS_NOTE not in body
    assert NO_ELEVATION_NOTE not in body
    assert RE_UPLOAD_SENTENCE not in body


@pytest.mark.django_db
@pytest.mark.parametrize("stage_count", [1, 3])
def test_rendering_the_stats_adds_no_query_beyond_fetching_the_track(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory, stage_count: int
) -> None:
    """The claim that stats are stored rather than re-derived, pinned as a query count.

    "Four column reads on a row the page already fetches, and no new query" is the reason
    these figures live in columns at all instead of being recomputed from the file on each
    view. Three docstrings assert it in prose and nothing enforced it: a later `.only()` on
    the track queryset, or any other deferral of the four columns, would turn those reads
    into a refresh query apiece on every page view and every other test here would pass.

    The count is absolute rather than a delta against a stats-free baseline, and it has to
    be: a deferral costs the *null* render exactly as many refresh queries as the populated
    one, so a delta cannot see it. That is why this number is worth updating by hand when
    the page legitimately gains a query — the failure message says which queries ran.

    Parametrized over one and three stages because the single-stage case cannot see the
    regression this page's move to multi-stage makes possible: a per-stage deferral costs
    one refresh query *per stage*, which is indistinguishable from the baseline where
    there is only one stage. The count is identical for both because `build_stages`
    materialises `ordered_stage_tracks` once with `list(...)` — that is the claim, and
    asserting it at a single stage was asserting it where it cannot fail.
    """
    for index in range(stage_count):
        make_gpx_track(
            trip,
            original_filename=f"alps-day-{index + 1}.gpx",
            distance_meters=42195.0,
            duration_seconds=8100.0,
            elevation_gain_meters=1240.4,
            elevation_loss_meters=1187.6,
        )
    url = detail_url(trip)
    auth_client.get(url)  # Warm the session so its lookups are not counted as a surprise.

    with CaptureQueriesContext(connection) as captured:
        body = auth_client.get(url).content.decode()

    assert "42.2 km" in body
    assert len(captured.captured_queries) == DETAIL_PAGE_QUERIES


def make_timed_track(
    trip: Trip,
    filename: str,
    started_at: datetime | None,
    ended_at: datetime | None,
) -> GpxTrack:
    """Persist a stage carrying its own instants, for the chronology-wording tests below.

    `make_gpx_track` (in `tests/conftest.py`) has no `started_at`/`ended_at` parameters —
    every existing caller is indifferent to ride order — so this stays local to the tests
    that actually need to control it.
    """
    return GpxTrack.objects.create(
        trip=trip,
        file=f"gpx/1/1/{filename}",
        points=GPX_POINTS,
        original_filename=filename,
        started_at=started_at,
        ended_at=ended_at,
        **GPX_BOUNDS,
    )


@pytest.mark.django_db
def test_a_multi_stage_trip_renders_each_stages_own_figures_not_the_newest_repeated(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """The forced correctness fix this phase exists for.

    Before this phase, both views handed `build_trip_stats` the newest track alone —
    shipping that untouched would print stage 3's distance under every stage's heading.
    Three distinct distances is what makes a "same number three times" regression visible.
    """
    make_gpx_track(trip, "day-1.gpx", distance_meters=10000.0)
    make_gpx_track(trip, "day-2.gpx", distance_meters=20000.0)
    make_gpx_track(trip, "day-3.gpx", distance_meters=30000.0)

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    stages = response.context["stages"]
    assert len(stages) == 3
    assert [stage.stats.distance for stage in stages] == ["10.0 km", "20.0 km", "30.0 km"]
    assert "10.0 km" in body
    assert "20.0 km" in body
    assert "30.0 km" in body


@pytest.mark.django_db
def test_each_stage_row_links_to_its_own_download_pk(
    auth_client: Client, trip: Trip, make_stored_track: StoredTrackFactory
) -> None:
    first = make_stored_track(trip, b"<gpx>1</gpx>", "day-1.gpx")
    second = make_stored_track(trip, b"<gpx>2</gpx>", "day-2.gpx")

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert f'href="{reverse("gpx:download", kwargs={"pk": first.pk})}"' in body
    assert f'href="{reverse("gpx:download", kwargs={"pk": second.pk})}"' in body


@pytest.mark.django_db
def test_the_stage_list_calls_itself_chronological_only_when_every_stage_is_timed(
    auth_client: Client, trip: Trip
) -> None:
    make_timed_track(
        trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 9, tzinfo=UTC)
    )
    make_timed_track(
        trip, "day-2.gpx", datetime(2026, 6, 2, 8, tzinfo=UTC), datetime(2026, 6, 2, 9, tzinfo=UTC)
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["chronology_established"] is True
    assert "Stages are shown in the order they were ridden." in body
    assert "these files carry no ride timestamps" not in body


@pytest.mark.django_db
def test_the_stage_list_falls_back_to_upload_order_wording_when_any_stage_is_untimed(
    auth_client: Client, trip: Trip
) -> None:
    """One untimed stage among timed ones is enough to withdraw the chronology claim.

    `chronology_is_established` requires *every* stage to carry a `started_at` — an
    upload-ordered boundary next to a ride-ordered one would have no real-world referent.
    """
    make_timed_track(
        trip, "day-1.gpx", datetime(2026, 6, 1, 8, tzinfo=UTC), datetime(2026, 6, 1, 9, tzinfo=UTC)
    )
    make_timed_track(trip, "day-2.gpx", None, None)

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert response.context["chronology_established"] is False
    assert "Stages are shown in upload order — these files carry no ride timestamps." in body
    assert "Stages are shown in the order they were ridden." not in body


@pytest.mark.django_db
def test_a_multi_stage_trip_shows_trip_totals_summed_above_a_collapsed_stages_section(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(
        trip,
        "day-1.gpx",
        distance_meters=10000.0,
        duration_seconds=3600.0,
        elevation_gain_meters=100.0,
        elevation_loss_meters=50.0,
    )
    make_gpx_track(
        trip,
        "day-2.gpx",
        distance_meters=20000.0,
        duration_seconds=3600.0,
        elevation_gain_meters=200.0,
        elevation_loss_meters=150.0,
    )

    response = auth_client.get(detail_url(trip))
    body = response.content.decode()

    assert response.status_code == 200
    assert TRIP_TOTALS_HEADING.search(body)
    assert STAGES_HEADING.search(body)
    assert body.index("Trip totals") < body.index(">Stages<")
    assert "Totals across 2 stages" in body
    assert "30.0 km" in body
    assert "2 h 00 min" in body
    assert "300 m" in body
    assert "200 m" in body


@pytest.mark.django_db
def test_a_stage_missing_one_figure_blanks_only_that_whole_trip_total(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(
        trip,
        "day-1.gpx",
        distance_meters=10000.0,
        duration_seconds=3600.0,
        elevation_gain_meters=100.0,
        elevation_loss_meters=50.0,
    )
    make_gpx_track(
        trip,
        "day-2.gpx",
        distance_meters=20000.0,
        duration_seconds=3600.0,
        elevation_loss_meters=150.0,
    )

    body = auth_client.get(detail_url(trip)).content.decode()

    assert "30.0 km" in body
    assert "2 h 00 min" in body
    assert NOT_EVERY_STAGE_NOTE in body
    assert "200 m" in body


@pytest.mark.django_db
def test_the_stages_section_starts_collapsed_with_a_no_js_fallback_toggle(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(trip, distance_meters=10000.0)

    body = auth_client.get(detail_url(trip)).content.decode()

    assert '<div class="collapse" id="stage-details">' in body
    assert 'class="collapse show"' not in body
    assert 'href="#stage-details"' in body
    assert 'aria-expanded="false"' in body
    assert 'class="btn btn-outline-secondary btn-sm mb-2 collapsed"' in body


@pytest.mark.django_db
def test_a_single_stage_trip_still_renders_the_trip_totals_block(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    make_gpx_track(
        trip,
        distance_meters=42195.0,
        duration_seconds=8100.0,
        elevation_gain_meters=1240.4,
        elevation_loss_meters=1187.6,
    )

    body = auth_client.get(detail_url(trip)).content.decode()

    assert TRIP_TOTALS_HEADING.search(body)
    assert "Totals across 1 stage" in body
    assert "Totals across 1 stages" not in body
    assert "42.2 km" in body
    assert "2 h 15 min" in body
    assert "1240 m" in body
    assert "1188 m" in body


@pytest.mark.django_db
def test_a_zero_stage_trip_renders_neither_totals_nor_stages_section(
    auth_client: Client, trip: Trip
) -> None:
    body = auth_client.get(detail_url(trip)).content.decode()

    assert TRIP_TOTALS_HEADING.search(body) is None
    assert STAGES_HEADING.search(body) is None


@pytest.mark.django_db
def test_a_rejected_upload_re_render_still_shows_the_whole_trip_totals(
    auth_client: Client, trip: Trip, make_gpx_track: TrackFactory
) -> None:
    """Context parity between `TripDetailView` and `GpxUploadView`'s error re-render."""
    make_gpx_track(
        trip,
        distance_meters=42195.0,
        duration_seconds=8100.0,
        elevation_gain_meters=1240.4,
        elevation_loss_meters=1187.6,
    )

    response = auth_client.post(
        reverse("gpx:upload", kwargs={"pk": trip.pk}),
        {"file": SimpleUploadedFile("notes.txt", b"not a gpx file", content_type="text/plain")},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert TRIP_TOTALS_HEADING.search(body)
    assert "42.2 km" in body
    assert "2 h 15 min" in body
    assert "1240 m" in body
    assert "1188 m" in body
