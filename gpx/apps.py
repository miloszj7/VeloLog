from django.apps import AppConfig


class GpxConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gpx"

    def ready(self) -> None:
        """Connect `gpx.signals`, which removes a track's file when its row is deleted.

        `INSTALLED_APPS` needs no entry for this — `"gpx"` resolves to this config through
        Django's app-config autodiscovery, and `ready()` is where a signal module is
        imported so the connection happens exactly once, after the app registry is
        populated.
        """
        # Imported for the side effect of running its `@receiver` decorator; the module
        # is never referenced by name, so F401 here is the intent rather than an oversight.
        from gpx import signals  # noqa: F401
