from typing import TYPE_CHECKING

from django.contrib import admin

from gpx.models import GpxTrack

if TYPE_CHECKING:
    _GpxTrackAdminBase = admin.ModelAdmin[GpxTrack]
else:
    _GpxTrackAdminBase = admin.ModelAdmin


@admin.register(GpxTrack)
class GpxTrackAdmin(_GpxTrackAdminBase):
    """Admin read/repair path for the GpxTrack model."""

    # `points` is deliberately absent from the changelist — it is unbounded data.
    list_display = ("original_filename", "trip", "uploaded_at")
    list_select_related = ("trip",)
    # The change form gets the same treatment as the changelist. A plain `trip` field
    # renders a <select> holding every Trip in the database across all users; `points`
    # renders its whole JSON payload into the page. Both grow without bound, so `trip`
    # becomes an id lookup and `points` leaves the form entirely. The cost is that
    # adding a GpxTrack by hand no longer works — `points` is NOT NULL with no default —
    # which is the intended direction: tracks arrive through the upload flow.
    raw_id_fields = ("trip",)
    exclude = ("points",)
    # `auto_now_add` already keeps this off the form; naming it here makes it visible.
    readonly_fields = ("uploaded_at",)
