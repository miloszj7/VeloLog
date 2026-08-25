from django.urls import path

from gpx import views

app_name = "gpx"

urlpatterns = [
    path("trips/<int:pk>/upload/", views.GpxUploadView.as_view(), name="upload"),
    path("tracks/<int:pk>/download/", views.GpxDownloadView.as_view(), name="download"),
]
