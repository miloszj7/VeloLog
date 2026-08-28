import secrets

from django.db import models

from trips.models import Trip


def gpx_upload_path(instance: "GpxTrack", filename: str) -> str:
    """Build the storage path for an uploaded track from trusted ids and random bytes.

    `filename` is user-supplied and deliberately unused: the security baseline forbids
    building a filesystem path from unsanitised input, and no ruff rule covers
    `upload_to`. The user's own name for the file survives in `original_filename`, never
    on disk. Must stay a module-level named function — it is serialised into the
    migration, so a lambda or closure would break `makemigrations`.
    """
    return f"gpx/{instance.trip.owner_id}/{instance.trip_id}/{secrets.token_hex(16)}.gpx"


class GpxTrack(models.Model):
    """A GPX file uploaded against a trip, plus the coordinates parsed out of it.

    The FK is deliberately many-tracks-per-trip so FR-011 needs no migration rewrite,
    even though v1 behaviour keeps exactly one track per trip. Points and bounds are
    derived once at upload, so rendering the detail page can never fail on a parse.
    """

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="tracks")
    file = models.FileField(upload_to=gpx_upload_path, max_length=255)
    points = models.JSONField()
    min_latitude = models.FloatField()
    min_longitude = models.FloatField()
    max_latitude = models.FloatField()
    max_longitude = models.FloatField()
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # Derived at upload alongside the points, for the same reason: the detail page reads
    # plain columns and can never fail on a parse. All four are `null=True` because rows
    # uploaded before these columns existed are backfilled best-effort, and because a
    # file that carried no `<ele>` or no `<time>` has no honest value to store — a `0`
    # there would read as "no climbing" rather than as "not recorded".
    #
    # `blank=True` is load-bearing, not decoration: `GpxTrackAdmin` excludes only
    # `points`, so without it these render as *required* on the admin change form and
    # break the documented admin repair path.
    distance_meters = models.FloatField(null=True, blank=True)
    duration_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Recorded time: the sum of each GPX segment's own span. Gaps between "
            "segments — including overnight gaps on a multi-day tour — are excluded, so "
            "this is not wall-clock elapsed time."
        ),
    )
    elevation_gain_meters = models.FloatField(null=True, blank=True)
    elevation_loss_meters = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self) -> str:
        return self.original_filename
