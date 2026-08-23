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
