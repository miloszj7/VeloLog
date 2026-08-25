from typing import TYPE_CHECKING

from django.contrib import admin

from trips.models import Trip

if TYPE_CHECKING:
    _TripAdminBase = admin.ModelAdmin[Trip]
else:
    _TripAdminBase = admin.ModelAdmin


@admin.register(Trip)
class TripAdmin(_TripAdminBase):
    """Admin read/repair path for the Trip model."""

    list_display = ("name", "date", "owner")
    list_select_related = ("owner",)
    # `Trip.get_absolute_url` would otherwise light up ModelAdmin's default
    # "View on site" link, which resolves to the owner-scoped detail route — so a
    # staff user inspecting another rider's trip lands on a 404 from their own admin.
    view_on_site = False
