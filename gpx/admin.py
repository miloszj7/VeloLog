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
