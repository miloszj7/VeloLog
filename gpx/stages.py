"""What are a trip's stages, in what order, and is that order evidence.

One module owning all three questions is what keeps the two render paths
(`trips/views.py` and `gpx/views.py`) from ordering a trip's stages two different ways,
and what keeps the three consumers of the chronology claim — the page's wording, the
stage-break markers, and the derived trip span — reading one predicate rather than three
independently-drifting flags.
"""

from collections.abc import Sequence

from django.db.models import F, QuerySet

from gpx.models import GpxTrack
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
    something real: the page may not call the order "chronological", stage-break markers
    must not be drawn (a break asserts the rider stopped here and resumed there, which
    upload order cannot evidence), and the derived trip span must not be shown (`Min`/
    `Max` skip NULLs, so a span over only the timed stages would be a lower bound
    presented as the whole).
    """
    return bool(tracks) and all(track.started_at is not None for track in tracks)
