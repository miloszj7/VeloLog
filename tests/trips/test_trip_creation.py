from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from trips.constants import FUTURE_TRIP_DATE_TOLERANCE
from trips.models import Trip


@pytest.mark.django_db
def test_valid_post_creates_trip_owned_by_requesting_user_and_redirects(
    auth_client: Client, rider: User
) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Alps Loop", "date": "2026-06-01", "description": "A week in the mountains."},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("trips:list")
    trip = Trip.objects.get(name="Alps Loop")
    assert trip.owner == rider


@pytest.mark.django_db
def test_empty_description_creates_trip(auth_client: Client) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Coastal Ride", "date": "2026-07-01", "description": ""},
    )

    assert response.status_code == 302
    trip = Trip.objects.get(name="Coastal Ride")
    assert trip.description == ""


@pytest.mark.django_db
def test_blank_name_rejects_and_creates_nothing(auth_client: Client) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {"name": "", "date": "2026-07-01", "description": ""},
    )

    assert response.status_code == 200
    assert response.context["form"].errors["name"]
    assert not Trip.objects.exists()


@pytest.mark.django_db
def test_posted_owner_field_cannot_override_server_side_assignment(
    auth_client: Client, rider: User, other_rider: User
) -> None:
    response = auth_client.post(
        reverse("trips:create"),
        {
            "name": "Alps Loop",
            "date": "2026-06-01",
            "description": "",
            "owner": other_rider.pk,
        },
    )

    assert response.status_code == 302
    trip = Trip.objects.get(name="Alps Loop")
    assert trip.owner == rider


@pytest.mark.django_db
def test_unauthenticated_post_redirects_to_login_and_creates_nothing(client: Client) -> None:
    response = client.post(
        reverse("trips:create"),
        {"name": "Alps Loop", "date": "2026-06-01", "description": ""},
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("login"))
    assert not Trip.objects.exists()


@pytest.mark.django_db
def test_unauthenticated_get_redirects_to_login(client: Client) -> None:
    response = client.get(reverse("trips:create"))

    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("login"))


@pytest.mark.django_db
def test_form_renders_cancel_link_to_trip_list(auth_client: Client) -> None:
    response = auth_client.get(reverse("trips:create"))

    assert response.status_code == 200
    body = response.content.decode()
    assert f'href="{reverse("trips:list")}"' in body
    assert ">Cancel<" in body


@pytest.mark.django_db
def test_far_future_date_rejects_and_creates_nothing(auth_client: Client) -> None:
    """`TripForm.date` had no negative path at all before E-08 closed."""
    next_year = timezone.localdate() + timedelta(days=365)

    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Planned Ride", "date": next_year.isoformat(), "description": ""},
    )

    assert response.status_code == 200
    assert response.context["form"].errors["date"]
    assert not Trip.objects.exists()


@pytest.mark.django_db
def test_todays_date_creates_trip(auth_client: Client) -> None:
    today = timezone.localdate()

    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Evening Spin", "date": today.isoformat(), "description": ""},
    )

    assert response.status_code == 302
    assert Trip.objects.get(name="Evening Spin").date == today


@pytest.mark.django_db
def test_one_day_ahead_is_accepted_because_the_tolerance_is_deliberate(
    auth_client: Client,
) -> None:
    """The `+1 day` slack is a timezone correction, not an off-by-one.

    `TIME_ZONE = "UTC"` makes `timezone.localdate()` the UTC date while the `type="date"`
    widget submits the rider's local one, so a rider east of UTC posting just after
    midnight is legitimately a day ahead. This test is what documents that as intended —
    without it, tightening the rule to `> localdate()` would look like a cleanup.

    The tolerance is asserted, not just used: both boundary tests derive their date from
    the same constant `TripForm.clean_date` reads, so widening it to five days would move
    the expectation with the code and leave both tests green. Pinning the value here is
    what makes the boundary a boundary in the other direction too.
    """
    assert FUTURE_TRIP_DATE_TOLERANCE == timedelta(days=1)
    tomorrow = timezone.localdate() + FUTURE_TRIP_DATE_TOLERANCE

    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Midnight Rider", "date": tomorrow.isoformat(), "description": ""},
    )

    assert response.status_code == 302
    assert Trip.objects.get(name="Midnight Rider").date == tomorrow


@pytest.mark.django_db
def test_one_day_past_the_tolerance_rejects_and_creates_nothing(auth_client: Client) -> None:
    """The far side of the boundary the test above pins down."""
    beyond = timezone.localdate() + FUTURE_TRIP_DATE_TOLERANCE + timedelta(days=1)

    response = auth_client.post(
        reverse("trips:create"),
        {"name": "Too Far Ahead", "date": beyond.isoformat(), "description": ""},
    )

    assert response.status_code == 200
    assert response.context["form"].errors["date"]
    assert not Trip.objects.exists()


@pytest.mark.django_db
def test_date_field_renders_its_help_text(auth_client: Client) -> None:
    """`Meta.help_texts` is silently ignored if misspelled singular, so assert the render.

    `ModelFormOptions` reads `help_texts`; a `help_text = {...}` typo raises nothing and
    renders nothing, and no lint, type or status-code check would notice. Asserting the
    sentence in the page body is the only gate standing between that typo and a green
    build — and the `id` proves the `aria-describedby` the widget now emits resolves.
    """
    response = auth_client.get(reverse("trips:create"))
    body = response.content.decode()

    assert response.status_code == 200
    assert "The day the ride happened" in body
    assert 'id="id_date_helptext"' in body
    assert 'aria-describedby="id_date_helptext"' in body


@pytest.mark.django_db
def test_put_is_rejected_as_a_disallowed_method(auth_client: Client) -> None:
    """The create page narrows its verbs for the reason the edit page does.

    Left at the default, `ProcessFormView.put` re-enters `post()` against an empty
    `request.POST` and returns a 200 re-render with every field in error — a page that
    reads as "you submitted this badly" for a request that was never a submission. The
    `Allow` assertion pins the pair of verbs that stay open.
    """
    response = auth_client.put(
        reverse("trips:create"),
        data="name=Alps+Loop&date=2026-06-01&description=",
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 405
    assert not Trip.objects.exists()
    allow = auth_client.options(reverse("trips:create")).headers["Allow"]
    assert allow == "GET, POST, HEAD, OPTIONS"
