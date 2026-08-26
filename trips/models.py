from django.conf import settings
from django.db import models
from django.urls import reverse


class Trip(models.Model):
    """A cycling trip owned by a user, aggregating a name, date, and description."""

    name = models.CharField(max_length=200)
    date = models.DateField()
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trips",
    )

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        """Return this trip's canonical detail URL.

        Every redirect that lands a user back on a trip resolves the route here, so
        the URL name lives in one place rather than being repeated across views.
        """
        return reverse("trips:detail", kwargs={"pk": self.pk})
