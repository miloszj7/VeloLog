from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from trips.models import Trip


@pytest.mark.django_db
def test_owner_get_prefills_the_form_with_the_trips_current_values(
    auth_client: Client, rider: User
) -> None:
    trip = Trip.objects.create(
        name="Alps Loop",
        date=date(2026, 6, 1),
        description="A week in the mountains.",
        owner=rider,
    )

    response = auth_client.get(reverse("trips:edit", kwargs={"pk": trip.pk}))
    initial = response.context["form"].initial

    assert response.status_code == 200
    assert initial["name"] == "Alps Loop"
    assert initial["date"] == date(2026, 6, 1)
    assert initial["description"] == "A week in the mountains."


@pytest.mark.django_db
def test_edit_page_is_headed_for_editing_and_cancels_back_to_the_trip(
    auth_client: Client, rider: User
) -> None:
    """The shared template must not call the edit page "New trip".

    `trips/trip_form.html` was written for the create flow and is `UpdateView`'s silent
    default, so every string that differs between the two flows is asserted here — this
    test is what fails if a branch is dropped.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.get(reverse("trips:edit", kwargs={"pk": trip.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    assert "<h1>Edit trip</h1>" in body
    assert "New trip" not in body
    assert "Save changes" in body
    assert f'<a href="{trip.get_absolute_url()}">Cancel</a>' in body


@pytest.mark.django_db
def test_detail_page_links_to_the_edit_form_and_the_list_page_does_not(
    auth_client: Client, rider: User
) -> None:
    """Edit is a detail-page control only — the list stays a list."""
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    edit_url = reverse("trips:edit", kwargs={"pk": trip.pk})

    detail = auth_client.get(trip.get_absolute_url())
    listing = auth_client.get(reverse("trips:list"))

    assert f'href="{edit_url}"' in detail.content.decode()
    assert f'href="{edit_url}"' not in listing.content.decode()


@pytest.mark.django_db
def test_valid_post_updates_the_trip_and_redirects_to_its_detail_page(
    auth_client: Client, rider: User
) -> None:
    trip = Trip.objects.create(
        name="Alps Loop",
        date=date(2026, 6, 1),
        description="A week in the mountains.",
        owner=rider,
    )

    response = auth_client.post(
        reverse("trips:edit", kwargs={"pk": trip.pk}),
        {"name": "Alps Grand Loop", "date": "2026-06-02", "description": "Ten days."},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == trip.get_absolute_url()
    trip.refresh_from_db()
    assert trip.name == "Alps Grand Loop"
    assert trip.date == date(2026, 6, 2)
    assert trip.description == "Ten days."


@pytest.mark.django_db
def test_success_message_renders_on_the_trip_page_after_edit(
    auth_client: Client, rider: User
) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    auth_client.post(
        reverse("trips:edit", kwargs={"pk": trip.pk}),
        {"name": "Alps Grand Loop", "date": "2026-06-01", "description": ""},
    )
    response = auth_client.get(trip.get_absolute_url())

    assert "Trip updated." in response.content.decode()


@pytest.mark.django_db
def test_blank_name_rejects_and_leaves_the_trip_unchanged(auth_client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.post(
        reverse("trips:edit", kwargs={"pk": trip.pk}),
        {"name": "", "date": "2026-06-01", "description": ""},
    )

    assert response.status_code == 200
    assert response.context["form"].errors["name"]
    trip.refresh_from_db()
    assert trip.name == "Alps Loop"


@pytest.mark.django_db
def test_posted_owner_field_cannot_reassign_the_trip(
    auth_client: Client, rider: User, other_rider: User
) -> None:
    """`owner` is not on the form, so posting it must be ignored rather than honoured.

    The create flow's equivalent guard lives in `test_trip_creation.py`; editing needs its
    own because a successful reassignment here would hand an existing trip away.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.post(
        reverse("trips:edit", kwargs={"pk": trip.pk}),
        {
            "name": "Alps Grand Loop",
            "date": "2026-06-01",
            "description": "",
            "owner": other_rider.pk,
        },
    )

    assert response.status_code == 302
    trip.refresh_from_db()
    assert trip.owner == rider


@pytest.mark.django_db
def test_another_users_trip_get_returns_404_and_leaks_nothing(
    auth_client: Client, other_rider: User
) -> None:
    other_trip = Trip.objects.create(
        name="Other Rider Trip", date=date(2026, 6, 1), owner=other_rider
    )

    response = auth_client.get(reverse("trips:edit", kwargs={"pk": other_trip.pk}))

    assert response.status_code == 404
    assert "Other Rider Trip" not in response.content.decode()


@pytest.mark.django_db
def test_another_users_trip_post_returns_404_and_changes_nothing(
    auth_client: Client, other_rider: User
) -> None:
    """The 404 alone would pass against a view that saved first and refused afterwards."""
    other_trip = Trip.objects.create(
        name="Other Rider Trip", date=date(2026, 6, 1), owner=other_rider
    )

    response = auth_client.post(
        reverse("trips:edit", kwargs={"pk": other_trip.pk}),
        {"name": "Stolen Trip", "date": "2026-07-01", "description": "Taken."},
    )

    assert response.status_code == 404
    other_trip.refresh_from_db()
    assert other_trip.name == "Other Rider Trip"
    assert other_trip.date == date(2026, 6, 1)
    assert other_trip.description == ""


@pytest.mark.django_db
def test_unauthenticated_get_redirects_to_login_with_next(client: Client, rider: User) -> None:
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    edit_url = reverse("trips:edit", kwargs={"pk": trip.pk})

    response = client.get(edit_url)

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('login')}?next={edit_url}"


@pytest.mark.django_db
def test_put_is_rejected_as_a_disallowed_method(auth_client: Client, rider: User) -> None:
    """Holds only because the view narrows `http_method_names`.

    Left at the default, `ProcessFormView.put` re-enters `post()` against an empty
    `request.POST` and returns a 200 re-render full of field errors. This test is what
    fails loudly the moment that narrowing is dropped.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)

    response = auth_client.put(
        reverse("trips:edit", kwargs={"pk": trip.pk}),
        data="name=Alps+Grand+Loop&date=2026-06-01&description=",
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 405
    trip.refresh_from_db()
    assert trip.name == "Alps Loop"


@pytest.mark.django_db
def test_head_and_options_are_served_like_the_page_they_describe(
    auth_client: Client, rider: User
) -> None:
    """`head` and `options` are in `http_method_names` on purpose, not by omission.

    `View.setup` aliases `head` to `get`, so a page-serving view answers HEAD for free —
    until the narrowing that closes `put` takes it away too. Narrowing to
    `["get", "post"]` made this one of only two pages in the app that 405 a HEAD an
    authenticated client is entitled to send. The `Allow` assertion is the other half:
    OPTIONS answering is worth nothing if it advertises a verb the view refuses.
    """
    trip = Trip.objects.create(name="Alps Loop", date=date(2026, 6, 1), owner=rider)
    url = reverse("trips:edit", kwargs={"pk": trip.pk})

    assert auth_client.head(url).status_code == 200

    options = auth_client.options(url)

    assert options.status_code == 200
    assert "PUT" not in options.headers["Allow"]


@pytest.mark.django_db
def test_name_of_a_future_dated_trip_can_be_edited_without_touching_its_date(
    auth_client: Client, rider: User
) -> None:
    """The `changed_data` escape in `clean_date`, which is what stops the rule trapping.

    Built via `Trip.objects.create` deliberately — the form is now what refuses to make a
    future-dated trip, so going through it could not set this fixture up. Trips like this
    exist for real: created through the admin, or before E-08 closed. Without the escape
    the rider could not fix this trip's name without also moving its date, and editing is
    the very capability this slice adds.
    """
    future = timezone.localdate() + timedelta(days=365)
    trip = Trip.objects.create(name="Alps Loop", date=future, owner=rider)

    response = auth_client.post(
        reverse("trips:edit", kwargs={"pk": trip.pk}),
        {"name": "Alps Grand Loop", "date": future.isoformat(), "description": ""},
    )

    assert response.status_code == 302
    trip.refresh_from_db()
    assert trip.name == "Alps Grand Loop"
    assert trip.date == future


@pytest.mark.django_db
def test_moving_a_future_dated_trip_to_another_future_date_is_rejected(
    auth_client: Client, rider: User
) -> None:
    """The escape is scoped to an *unchanged* date — it is not an exemption for the trip."""
    future = timezone.localdate() + timedelta(days=365)
    trip = Trip.objects.create(name="Alps Loop", date=future, owner=rider)

    response = auth_client.post(
        reverse("trips:edit", kwargs={"pk": trip.pk}),
        {
            "name": "Alps Loop",
            "date": (future + timedelta(days=1)).isoformat(),
            "description": "",
        },
    )

    assert response.status_code == 200
    assert response.context["form"].errors["date"]
    trip.refresh_from_db()
    assert trip.date == future
