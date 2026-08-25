import pytest
from django.contrib.auth.models import User

from trips.models import Trip


@pytest.mark.django_db
def test_trip_saves_with_owner_and_is_reachable_via_reverse_accessor(rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", description="", owner=rider)

    assert trip in rider.trips.all()


@pytest.mark.django_db
def test_trip_saves_with_empty_description(rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", description="", owner=rider)

    assert trip.description == ""


@pytest.mark.django_db
def test_trips_with_different_dates_come_back_newest_first(rider: User) -> None:
    older = Trip.objects.create(name="Older Trip", date="2026-01-01", owner=rider)
    newer = Trip.objects.create(name="Newer Trip", date="2026-06-01", owner=rider)

    trips = list(Trip.objects.all())

    assert trips == [newer, older]


@pytest.mark.django_db
def test_trips_sharing_a_date_come_back_in_deterministic_order(rider: User) -> None:
    first = Trip.objects.create(name="First Trip", date="2026-06-01", owner=rider)
    second = Trip.objects.create(name="Second Trip", date="2026-06-01", owner=rider)

    trips = list(Trip.objects.all())

    assert trips == [second, first]


@pytest.mark.django_db
def test_get_absolute_url_points_at_the_trips_detail_route(rider: User) -> None:
    """Asserts the URL *shape*, not just its name.

    Comparing against `reverse("trips:detail", ...)` would restate the implementation's
    own call, so both sides would move together and a route path change that breaks
    existing bookmarks would pass green.
    """
    trip = Trip.objects.create(name="Alps Loop", date="2026-06-01", owner=rider)

    assert trip.get_absolute_url() == f"/trips/{trip.pk}/"
