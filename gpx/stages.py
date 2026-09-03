"""What are a trip's stages, in what order, is that order evidence, and what does it span.

One module owning all four questions is what keeps the two render paths
(`trips/views.py` and `gpx/views.py`) from ordering a trip's stages two different ways,
and what keeps the three consumers of the chronology claim — the page's wording, the
stage-break markers, and the derived trip span — reading one predicate rather than three
independently-drifting flags.

The span is derived here on every render and stored nowhere. That is the reasoning that
closed roadmap item E-10: a stored `(start, end)` pair would be a second source of truth
for something the stage instants already answer, and its only novel behaviour would be
drift. `Trip.date` stays exactly what it was — the day the tour started, supplied by the
rider — and is what the page falls back to whenever the instants cannot evidence a span.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from django.db.models import F, QuerySet

from gpx.availability import track_file_is_available
from gpx.constants import STAGE_COLORS
from gpx.models import GpxTrack
from gpx.statistics import TripStats, build_trip_stats
from trips.models import Trip


def ordered_stage_tracks(trip: Trip) -> QuerySet[GpxTrack]:
    """Return `trip`'s stages in ride order where it is known, upload order otherwise.

    Not `COALESCE(started_at, uploaded_at)` into one sort key: that would compare a ride
    instant against an upload instant, so an untimed stage uploaded in January would sort
    ahead of a timed stage ridden in June — a deterministic answer, but a meaningless one.
    The three-term `order_by` below handles all-timed, none-timed and mixed trips without
    branching: timed stages sort first, by their own `started_at`; untimed stages follow,
    in the order they were uploaded.
    """
    return trip.tracks.order_by(F("started_at").asc(nulls_last=True), "uploaded_at", "id")


def chronology_is_established(tracks: Sequence[GpxTrack]) -> bool:
    """Whether `tracks`' order is a ride-order claim, not merely an upload-order one.

    True only when there is at least one stage and every one of them carries a
    `started_at`. A single untimed stage is not established — nothing about its position
    is a chronology claim either way — and neither is an empty trip.

    This predicate gates every claim downstream that depends on the order meaning
    something real. Three exist: the page may not call the order "chronological",
    stage-break markers must not be drawn (a break asserts the rider stopped here and
    resumed there, which upload order cannot evidence), and no trip span may be shown —
    `min`/`max` skip nothing here, but a span computed over the timed subset of a
    partially timed trip is a lower bound that would be presented as the whole. That
    third one is `trip_span` below, which calls this rather than carrying its own gate.
    """
    return bool(tracks) and all(track.started_at is not None for track in tracks)


def trip_span(tracks: Sequence[GpxTrack]) -> tuple[datetime, datetime] | None:
    """Return the tour's real span, or `None` when the stages cannot evidence one.

    Args:
        tracks: The trip's stages, in any order — `min`/`max` do not care, and taking
            tracks rather than `Stage`s is what lets this share one gate with
            `chronology_is_established` instead of re-deriving the claim from a
            differently-shaped input.

    Returns:
        `(first start, last end)` when every stage is timed, `None` otherwise. `None` is
        not a degraded span: it is the instruction to show `Trip.date` alone, which is
        exactly what the page rendered before any of this existed, so the fallback needed
        no new UI and cannot look broken.

    The second `None` case is narrower and worth naming, because the parse boundary
    forbids it: a stage carrying `started_at` but not `ended_at`. `gpx/parsing.py` stores
    both instants or neither, so no upload produces such a row — but the admin change
    form exposes both fields individually and is the documented repair path, so one hand
    edit can. Returning `None` there keeps a half-edited row showing the stored date
    instead of raising `TypeError` out of `max()` on the detail page. It is a guard on
    hand-edited data, not a second chronology rule: `chronology_is_established` above
    remains the only place the claim itself is decided.
    """
    if not chronology_is_established(tracks):
        return None
    # The comprehension filters are what make these `list[datetime]` rather than
    # `list[datetime | None]` under `mypy --strict`; the predicate above is what
    # guarantees `starts` ends up non-empty and the same length as `tracks`.
    starts = [track.started_at for track in tracks if track.started_at is not None]
    ends = [track.ended_at for track in tracks if track.ended_at is not None]
    if len(ends) != len(tracks):
        return None
    return min(starts), max(ends)


@dataclass(frozen=True)
class Stage:
    """One trip stage as both render paths need it: its track, position and own figures.

    A frozen dataclass rather than two separate lookups, so the map payload and the
    stage-list template read one structure and cannot disagree about which colour belongs
    to which track.
    """

    track: GpxTrack
    number: int
    """1-based position in ride order — `Stage {{ stage.number }}` reads directly off it."""
    color: str
    """One of `STAGE_COLORS`, cycled by `number - 1` so stage 7 reuses stage 1's colour."""
    stats: TripStats | None
    file_available: bool


def build_stages(trip: Trip) -> tuple[Stage, ...]:
    """Return `trip`'s stages in ride order, each carrying its own colour and figures.

    `build_trip_stats` and `track_file_is_available` keep their single-track signatures —
    they are called once per stage here rather than widened, so neither helper's own
    tests need to know about stages at all.
    """
    tracks = list(ordered_stage_tracks(trip))
    return tuple(
        Stage(
            track=track,
            number=index + 1,
            color=STAGE_COLORS[index % len(STAGE_COLORS)],
            stats=build_trip_stats(track),
            file_available=track_file_is_available(track),
        )
        for index, track in enumerate(tracks)
    )
