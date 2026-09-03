"""What are a trip's stages, in what order, and is that order evidence.

One module owning all three questions is what keeps the two render paths
(`trips/views.py` and `gpx/views.py`) from ordering a trip's stages two different ways,
and what keeps the two consumers of the chronology claim — the page's wording and the
stage-break markers — reading one predicate rather than two independently-drifting flags.

A derived trip span would be the third, and is deliberately *not* here: it is the plan's
Phase 7, which was cut. When it arrives it reads this same predicate rather than growing
its own gate — see `chronology_is_established` for why.
"""

from collections.abc import Sequence
from dataclasses import dataclass

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
    something real. Two exist today: the page may not call the order "chronological", and
    stage-break markers must not be drawn (a break asserts the rider stopped here and
    resumed there, which upload order cannot evidence).

    A third is a standing constraint on work not yet done rather than a description of
    this codebase: **if a trip span is ever derived from these instants, it must be gated
    here too.** `Min`/`Max` skip NULLs, so a span computed over a partially timed trip is
    a lower bound that would be presented as the whole. Nothing derives a span today.
    """
    return bool(tracks) and all(track.started_at is not None for track in tracks)


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
