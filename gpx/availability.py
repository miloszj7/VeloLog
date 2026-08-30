"""Answers whether a track's file can actually be read back from storage.

Built here rather than in either view because two views render the trip detail page:
`TripDetailView` on a normal visit, and `GpxUploadView` when it re-renders that page with
a form error. A helper reachable from only one of them would leave the other rendering the
"file unavailable" branch over a perfectly healthy track — the exact drift `build_map_config`
and `build_trip_stats` already exist to prevent for the map and stats blobs.
"""

from gpx.models import GpxTrack


def track_file_is_available(track: GpxTrack | None) -> bool:
    """Return whether `track`'s stored file actually exists in storage.

    Args:
        track: The trip's current track, or `None` when nothing has been uploaded.

    Returns:
        `False` when there is no track or its stored file name is empty — the "never
        stored" row shape — otherwise the storage backend's own existence check for
        that file name.
    """
    if track is None or not track.file.name:
        return False
    return track.file.storage.exists(track.file.name)
