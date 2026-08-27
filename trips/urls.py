from django.urls import path

from trips import views

app_name = "trips"

urlpatterns = [
    path("", views.TripListView.as_view(), name="list"),
    path("new/", views.TripCreateView.as_view(), name="create"),
    path("<int:pk>/", views.TripDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.TripUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.TripDeleteView.as_view(), name="delete"),
]
