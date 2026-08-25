from django.urls import path

from gpx import views

app_name = "gpx"

# These routes are mounted under `/gpx/`, so the upload one reads `/gpx/trips/<pk>/upload/`
# and repeats a segment that `trips/urls.py` already owns. It is namespaced by the code's
# home package rather than by the resource it acts on, which is the opposite of the usual
# convention and the opposite of where a reader looking for "everything that acts on a trip"
# would go. Kept deliberately: the URL is reached only through `{% url %}` in a template and
# `reverse()` in tests, never typed, and moving it after the first uploads exist would break
# links riders may have kept. Re-home it under `/trips/` if this app ever grows a route that
# makes the split confusing enough to be worth the redirect.

urlpatterns = [
    path("trips/<int:pk>/upload/", views.GpxUploadView.as_view(), name="upload"),
    path("tracks/<int:pk>/download/", views.GpxDownloadView.as_view(), name="download"),
]
