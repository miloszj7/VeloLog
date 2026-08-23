import pytest
from django.contrib.auth.models import User

from trips.models import Trip


@pytest.mark.django_db
def test_trip_saves_with_owner_and_is_reachable_via_reverse_accessor() -> None:
    user = User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", description="", owner=user)

    assert trip in user.trips.all()


@pytest.mark.django_db
def test_trip_saves_with_empty_description() -> None:
    user = User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", description="", owner=user)

    assert trip.description == ""


@pytest.mark.django_db
def test_trips_with_different_dates_come_back_newest_first() -> None:
    user = User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    older = Trip.objects.create(name="Older Trip", date="2026-01-01", owner=user)
    newer = Trip.objects.create(name="Newer Trip", date="2026-06-01", owner=user)

    trips = list(Trip.objects.all())

    assert trips == [newer, older]


@pytest.mark.django_db
def test_trips_sharing_a_date_come_back_in_deterministic_order() -> None:
    user = User.objects.create_user(username="rider", password="correct-horse-battery-staple")
    first = Trip.objects.create(name="First Trip", date="2026-06-01", owner=user)
    second = Trip.objects.create(name="Second Trip", date="2026-06-01", owner=user)

    trips = list(Trip.objects.all())

    assert trips == [second, first]
