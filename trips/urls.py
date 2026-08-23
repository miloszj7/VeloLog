from django.urls import path

from trips import views

app_name = "trips"

urlpatterns = [
    path("", views.TripListView.as_view(), name="list"),
    path("new/", views.TripCreateView.as_view(), name="create"),
]
