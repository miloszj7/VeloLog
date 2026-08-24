"""
URL configuration for velo_log project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import logging
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.sessions.backends.db import SessionStore
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView

logger = logging.getLogger(__name__)

# A single fixed key, deliberately not a generated one. /healthz/ is unauthenticated, so
# every anonymous probe runs this round-trip; with a generated name, a delete that started
# failing would silently accumulate files on the very Volume the app depends on. A fixed
# key bounds that: at most one file survives a probe that died before its cleanup ran, and
# the next probe reclaims it. The bound holds only because each probe deletes the name its
# own `save` returned — see `_media_round_trips`.
HEALTHZ_MEDIA_KEY = "healthz/probe.txt"
HEALTHZ_MEDIA_PAYLOAD = b"velolog-healthz"


def _database_round_trips() -> bool:
    """Write and read a session row back to confirm the database is reachable."""
    try:
        store = SessionStore()
        store["healthz"] = "ok"
        store.save()
        readback = SessionStore(session_key=store.session_key)
        ok = readback.get("healthz") == "ok"
        readback.delete()
        return ok
    except Exception:
        logger.exception("healthz: database round-trip failed")
        return False


def _media_root_misconfigured() -> str | None:
    """Return why MEDIA_ROOT is unusable in production, or None when it is fine.

    Writability alone proves nothing: with MEDIA_ROOT unset the default is
    BASE_DIR / "media" *inside the container*, where a write succeeds — so a
    writability-only probe returns 200 while every uploaded file sits on ephemeral disk
    and is lost on the next redeploy (infrastructure.md:59). Under DEBUG that local
    default is the intended arrangement, so the assertion is skipped there.
    """
    if settings.DEBUG:
        return None
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.is_absolute():
        return f"MEDIA_ROOT {settings.MEDIA_ROOT!r} is not an absolute path"
    if media_root.resolve().is_relative_to(Path(settings.BASE_DIR).resolve()):
        return (
            f"MEDIA_ROOT {settings.MEDIA_ROOT!r} resolves inside BASE_DIR — uploads would "
            "land on ephemeral container disk instead of the mounted volume"
        )
    return None


def _media_round_trips() -> bool:
    """Write, read back and delete a probe file through `default_storage`.

    `Storage.save` always routes through `get_available_name`, so the opening delete only
    frees the key — it cannot keep the write off the suffix path. A concurrent probe that
    re-takes the key in that window sends this write to `probe_<suffix>.txt`, so the name
    `save` *returns* is the only one this call may read back or delete: reading the
    constant key instead reports on someone else's bytes, and deleting it strands this
    probe's file on the Volume for good. The delete sits in `finally` so a failed
    read-back still cleans up after itself.
    """
    saved: str | None = None
    try:
        # Reclaims a file stranded by a probe that died before its own cleanup ran.
        default_storage.delete(HEALTHZ_MEDIA_KEY)
        saved = default_storage.save(HEALTHZ_MEDIA_KEY, ContentFile(HEALTHZ_MEDIA_PAYLOAD))
        with default_storage.open(saved, "rb") as handle:
            return bool(handle.read() == HEALTHZ_MEDIA_PAYLOAD)
    except Exception:
        logger.exception("healthz: media round-trip failed")
        return False
    finally:
        if saved is not None:
            try:
                default_storage.delete(saved)
            except Exception:
                logger.exception("healthz: could not clean up the media probe file")


def healthz(request: HttpRequest) -> HttpResponse:
    """Report whether the database and the media store are both reachable and correct.

    Each subsystem gets its own verdict rather than collapsing into one boolean, so an
    operator can tell from the response body alone which half failed. The media root is
    checked for *location* before anything is written to it — a misconfigured root must
    not be created and written to just to prove it was writable.
    """
    database_ok = _database_round_trips()
    misconfigured = _media_root_misconfigured()
    media_ok = misconfigured is None and _media_round_trips()
    ok = database_ok and media_ok

    payload = {
        "status": "ok" if ok else "error",
        "database": "ok" if database_ok else "error",
        "media": "ok" if media_ok else "error",
        "media_root": str(settings.MEDIA_ROOT),
    }
    if misconfigured is not None:
        payload["media_error"] = misconfigured
    return JsonResponse(payload, status=200 if ok else 500)


urlpatterns = [
    path("", RedirectView.as_view(url=reverse_lazy("trips:list"), permanent=False)),
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("accounts/", include("accounts.urls")),
    path(
        "accounts/login/",
        LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("trips/", include("trips.urls")),
]
