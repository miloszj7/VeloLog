"""The data-isolation contract: who may reach an object by pk, and what a refusal looks like.

This project's entire authorization story is one idiom — every view that exposes an object
by pk filters its queryset by owner rather than fetching the row and then comparing. It is
hand-copied across five views with no shared base (`trips/views.py:48,74,122,153`,
`gpx/views.py:56`), so nothing structural forces a sixth view to follow. That — not any
present defect — is what this module exists to guard.

Four separate contracts meet here, and they cannot be collapsed into one assertion because
each is produced by a different mechanism and fails in a different way:

1. **404 for an authenticated non-owner.** Produced by the owner-scoped queryset. Never 403:
   a 403 would confirm the pk exists, which is the disclosure the 404 exists to prevent.
2. **302 to the login page, with an exact `?next=`, for anonymous.** Produced by
   `LoginRequiredMixin`, an entirely different mechanism — an ownership regression is
   invisible on this leg and a mixin-ordering regression is invisible on the leg above.
3. **An answer given before the object is ever looked up.** Two verbs land here, both
   resolved by `View.dispatch` ahead of `get_queryset`, so both are identical for a real and
   a nonexistent pk and neither discloses anything: **405** for a verb outside
   `http_method_names`, and **200 with an `Allow` header and an empty body** for `OPTIONS`,
   which `View.options` answers from the class's verb list alone. The 405 leg is a security
   control rather than a style preference — `trips/views.py:151` left at its default lets a
   raw `DELETE` destroy a trip and its GPX file with no confirmation page. The `OPTIONS` leg
   is asserted *as* a non-disclosure: the same request against a pk that does not exist must
   produce the same bytes, which is what makes a 200 acceptable where 404 is the rule.
4. **No route at all under `MEDIA_URL`.** Not a contract about a response — a contract about
   the *absence* of a route, which is the least-testable kind of guarantee and the one
   nothing in this suite had ever exercised as a request.

Two consequences shape everything below.

**A status code alone is never enough.** `gpx:download` answers 404 for three distinct
causes — not yours, does not exist, and file missing from storage (`gpx/views.py:140-153`) —
so a cell asserting only `== 404` cannot tell a working guard from a broken one. Every cell
pairs its status with a *probe*: a state or no-leak assertion that would fail against a view
that did the work and refused afterwards (`tests/trips/test_trip_edit.py:167`).

**The inventory itself is asserted.** `OBJECT_SCOPED_ROUTES` below is a declared list of
every object-scoped route, and `test_every_object_scoped_route_is_classified` compares it
against what the URLconf actually exposes. A sixth route added without the idiom turns this
module red instead of shipping green.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, cast

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse, HttpResponseBase, StreamingHttpResponse
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from gpx.models import GpxTrack
from tests.conftest import StoredTrackFactory
from trips.models import Trip

# The converter string every object-scoped pattern in this project uses. Matched as a
# substring of the route rather than by parsing, because the route is what a contributor
# writes and what a reviewer reads.
PK_CONVERTER = "<int:pk>"

# The two namespaces that own user data. `accounts` and the project-level routes carry no
# object pk, and `admin` is deliberately cross-user (see the admin cells, added in Phase 3).
GUARDED_NAMESPACES = ("trips", "gpx")


@dataclass(frozen=True)
class TargetObjects:
    """The data a cell aims at — owned by somebody other than the requesting client.

    `track` and `track_content` are absent for the trip-only routes. A probe that needs them
    asserts their presence itself rather than degrading to a silent pass, so a cell built
    with the cheap `make_gpx_track` where it needed real bytes fails loudly.
    """

    trip: Trip
    track: GpxTrack | None = None
    track_content: bytes | None = None


# What a cell asserts *besides* the status code. Takes the objects the request was aimed at
# and the response it produced, and raises `AssertionError` if anything leaked or moved.
Probe = Callable[[TargetObjects, HttpResponseBase], None]


# Where a drained streaming body is memoized on the response itself. See `_body`.
_DRAINED_BODY_ATTR = "_ownership_matrix_drained_body"


def _body(response: HttpResponseBase) -> bytes:
    """Return a response's bytes, draining a streaming response rather than skipping it.

    `gpx:download` answers with a `FileResponse`, so the one response shape that could
    actually leak a foreign rider's track is the streaming one. Reading `.content` on it
    raises; returning `b""` for it would turn the leak probe into a guaranteed pass.

    The result is memoized on the response because `streaming_content` is a one-shot
    iterator: drained once, every later read yields `b""`. That is the same guaranteed pass
    by a different route — a cell that checks a status, then asks a probe to search the
    body, would have the probe searching nothing. Memoizing makes a second read return what
    the first one saw, so the number of times a body is consulted stops being load-bearing.

    `streaming_content` is typed as sync-or-async; the cast picks the sync half, which is
    what a `FileResponse` built by `GpxDownloadView` under the sync test client always is.
    """
    if isinstance(response, StreamingHttpResponse):
        cached = getattr(response, _DRAINED_BODY_ATTR, None)
        if cached is None:
            cached = b"".join(cast(Iterator[bytes], response.streaming_content))
            setattr(response, _DRAINED_BODY_ATTR, cached)
        return cast(bytes, cached)
    return cast(HttpResponse, response).content


def _assert_trip_neither_leaked_nor_mutated(
    target: TargetObjects, response: HttpResponseBase
) -> None:
    """The trip is absent from the body, still exists, and holds the values it started with.

    Three assertions rather than one because the routes this probes fail in three ways:
    `trips:detail` and `trips:edit` would leak the trip into the body, `trips:edit` would
    save it, and `trips:delete` would destroy it. The existence check is the leg that carries
    `trips:delete`, and it is a `filter().first()` rather than a `get()` so a deleted trip
    reports as a contract violation instead of a `DoesNotExist` traceback.

    `target.trip` is the pre-request in-memory copy and is never refreshed, so comparing the
    stored row against it is a genuine before/after comparison. HEAD and OPTIONS answer with
    an empty body, which the leak leg passes on correctly rather than being skipped for.
    """
    assert target.trip.name.encode() not in _body(response), (
        f"the response body contains {target.trip.name!r}, a trip owned by another rider — "
        f"the owner-scoped queryset is no longer the only thing deciding what is rendered"
    )
    stored = Trip.objects.filter(pk=target.trip.pk).first()
    assert stored is not None, (
        f"trip {target.trip.pk}, owned by another rider, no longer exists — a request from a "
        f"non-owner destroyed it"
    )
    assert (stored.name, stored.date, stored.description) == (
        target.trip.name,
        target.trip.date,
        target.trip.description,
    ), (
        f"trip {target.trip.pk}, owned by another rider, was modified by a request from a "
        f"non-owner — the refusal happened after the write, not before it"
    )


def _assert_no_track_was_attached(target: TargetObjects, response: HttpResponseBase) -> None:
    """The upload target gained no track, and its name did not reach the body.

    `GpxUploadView.post` resolves the trip through an owner-scoped queryset before the form
    is touched (`gpx/views.py:46-54`); this is what fails if that ordering is ever inverted,
    because a form run first would persist the row before the ownership check refused.
    """
    attached = list(target.trip.tracks.values_list("pk", flat=True))
    expected = [] if target.track is None else [target.track.pk]
    assert attached == expected, (
        f"trip {target.trip.pk}, owned by another rider, now carries tracks {attached} rather "
        f"than {expected} — a non-owner's upload was persisted before it was refused"
    )
    assert target.trip.name.encode() not in _body(response), (
        f"the response body contains {target.trip.name!r}, a trip owned by another rider — a "
        f"re-rendered error page confirms the trip exists"
    )


def _assert_track_bytes_were_not_served(target: TargetObjects, response: HttpResponseBase) -> None:
    """The foreign track's stored bytes are absent from the response.

    The load-bearing probe of the pair, because `gpx:download` answers 404 for three distinct
    causes and a status-only cell cannot tell the working guard from a route that 404s for
    an unrelated reason. Direct precedent: this route's original cross-user test was
    status-code-only and was corrected to assert the bytes
    (`context/archive/2026-08-23-upload-gpx-and-view-map/reviews/impl-review-phase-4.md:200-216`).
    """
    assert target.track is not None and target.track_content is not None, (
        "this cell probes for served bytes, so it must be built with `make_stored_track` and "
        "the distinctive content passed on the descriptor — without both, the probe would "
        "pass against a route that served the file"
    )
    assert target.track_content not in _body(response), (
        f"the response body contains the stored bytes of track {target.track.pk}, owned by "
        f"another rider — the file was served to a client with no claim to it"
    )


@dataclass(frozen=True)
class ObjectScopedRoute:
    """One route that exposes a user-owned object by pk, and what a cell needs to know of it.

    `pk_object` exists because the pk is not always a trip's: `gpx:download` takes a
    `GpxTrack` pk and reaches its owner through `trip__owner`, the only such traversal in the
    project (`GpxTrack` carries no user FK).

    `accepted_verbs` is the view's real answer set, not its `http_method_names` list —
    `TripDetailView` narrows nothing yet still 405s a POST, because `View.dispatch` resolves
    a handler by method name and there is no `post` to find.
    """

    name: str
    pk_object: Literal["trip", "track"]
    accepted_verbs: tuple[str, ...]
    probe: Probe


# The inventory. `test_every_object_scoped_route_is_classified` below asserts this is the
# whole of it; the matrix cells are parametrized from it. Adding a route means adding a row
# here — with the probe that says what "refused" means for it — not just a URL.
OBJECT_SCOPED_ROUTES = (
    ObjectScopedRoute(
        # No `http_method_names` narrowing (`trips/views.py:71`); only `get` is defined, so
        # `head` (aliased to it by `View.setup`) and the inherited `options` come along.
        name="trips:detail",
        pk_object="trip",
        accepted_verbs=("get", "head", "options"),
        probe=_assert_trip_neither_leaked_nor_mutated,
    ),
    ObjectScopedRoute(
        # `trips/views.py:120` — PUT is excluded deliberately: left in, `ProcessFormView.put`
        # re-enters `post()` against an empty `request.POST` and 200s with every field in error.
        name="trips:edit",
        pk_object="trip",
        accepted_verbs=("get", "post", "head", "options"),
        probe=_assert_trip_neither_leaked_nor_mutated,
    ),
    ObjectScopedRoute(
        # `trips/views.py:151` — DELETE is excluded deliberately, and this is the narrowing
        # that is a security control: `DeletionMixin.delete()` would otherwise run straight to
        # `self.object.delete()` without ever rendering the confirmation page.
        name="trips:delete",
        pk_object="trip",
        accepted_verbs=("get", "post", "head", "options"),
        probe=_assert_trip_neither_leaked_nor_mutated,
    ),
    ObjectScopedRoute(
        # `gpx/views.py:42` — POST only. The URL is nothing but the detail page's form target,
        # so even OPTIONS is refused.
        name="gpx:upload",
        pk_object="trip",
        accepted_verbs=("post",),
        probe=_assert_no_track_was_attached,
    ),
    ObjectScopedRoute(
        # `gpx/views.py:122` — a plain `View` defining only `get`, so the answer set matches
        # `trips:detail`'s for the same reason rather than by narrowing.
        name="gpx:download",
        pk_object="track",
        accepted_verbs=("get", "head", "options"),
        probe=_assert_track_bytes_were_not_served,
    ),
)


def _pk_routes_under(resolver: URLResolver, prefix: str) -> set[str]:
    """Collect the namespaced names of every pk-bearing pattern below one resolver.

    Recursive rather than a single flat pass over `trips.urls` and `gpx.urls`: neither
    includes another URLconf today, and a nested include added later must not be able to
    hide an object-scoped route from the guard by being one level deeper than it looked for.
    """
    routes: set[str] = set()
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            nested = f"{prefix}:{entry.namespace}" if entry.namespace else prefix
            routes |= _pk_routes_under(entry, nested)
        elif isinstance(entry, URLPattern) and entry.name and PK_CONVERTER in str(entry.pattern):
            routes.add(f"{prefix}:{entry.name}")
    return routes


def _routes_exposed_by_the_urlconf() -> set[str]:
    """Every `<int:pk>` route the project actually serves under `trips` or `gpx`."""
    routes: set[str] = set()
    for entry in get_resolver().url_patterns:
        if isinstance(entry, URLResolver) and entry.namespace in GUARDED_NAMESPACES:
            routes |= _pk_routes_under(entry, entry.namespace)
    return routes


def test_every_object_scoped_route_is_classified() -> None:
    """The declared inventory is the whole inventory — nothing reaches an object unclassified.

    This is the one test in the module that guards the *future* rather than the present. No
    route is unfiltered today; all five scope their queryset by owner. What nothing enforces
    is that route number six does too, because the idiom is copy-pasted rather than inherited
    from a shared base. Without this test a new `<int:pk>` view ships green with no cell
    proving it refuses a non-owner.

    Compared as namespaced names rather than view classes so the failure speaks the same
    vocabulary as `reverse()` and as `OBJECT_SCOPED_ROUTES` itself.
    """
    declared = {route.name for route in OBJECT_SCOPED_ROUTES}
    exposed = _routes_exposed_by_the_urlconf()

    unclassified = exposed - declared
    stale = declared - exposed

    assert not unclassified, (
        f"{sorted(unclassified)} expose an object by pk under {GUARDED_NAMESPACES} but are "
        f"absent from OBJECT_SCOPED_ROUTES, so nothing proves they scope their queryset by "
        f"owner — one user could read, modify or delete another's data through them. Add a "
        f"row (with the probe that says what a refusal means for the route), or, if the route "
        f"is genuinely public, add an explicit allowlist constant saying so"
    )
    assert not stale, (
        f"{sorted(stale)} are declared in OBJECT_SCOPED_ROUTES but no longer exist in the "
        f"URLconf, so the cells parametrized from them cannot be reversed — drop the rows"
    )


# --------------------------------------------------------------------------------------
# The matrix: every declared route × every actor × every verb.
# --------------------------------------------------------------------------------------

# The name every target trip carries. Escape-free by contract, and that is not cosmetic:
# a leak assertion on `"Other's Trip"` once passed while the trip was on screen, because
# Django autoescaped the apostrophe into `&#x27;` and the raw needle no longer matched
# (`context/archive/2026-08-23-create-and-list-trips/reviews/impl-review.md:59-76`). The
# wording says what the cell is proving rather than who owns it, because the same constant
# builds the reverse-direction targets, where the owner is the *first* rider.
TARGET_TRIP_NAME = "Unreachable Rider Trip"
TARGET_TRIP_DATE = date(2026, 6, 1)

# Distinctive bytes so `_assert_track_bytes_were_not_served` fails on *this* file rather
# than on anything GPX-shaped. Deliberately not valid GPX: nothing in this module parses
# it — `make_stored_track` writes the bytes and sets the map columns directly, and every
# cell here is a refusal, so no code path ever reads it back.
TARGET_TRACK_CONTENT = b"<gpx><!-- unreachable-rider-track --></gpx>"

# The verbs each route is swept with. Every one a route does not accept becomes a
# rejected-verb cell, so this tuple decides the width of that half of the matrix.
# `trace` is left out on purpose: no view defines a handler for it, so it would add five
# cells that all pass for a reason unrelated to ownership.
PROBED_VERBS = ("get", "post", "head", "options", "put", "patch", "delete")

# `View.options` answers from the class's verb list without touching `get_queryset`, so it
# is the one accepted verb that does not 404 for a non-owner. It is split out rather than
# excused: it gets its own cell asserting the response is metadata and nothing else.
METADATA_VERB = "options"

# (route, verb) for every verb a route answers. The anonymous sweep uses all of it —
# `LoginRequiredMixin.dispatch` runs ahead of the method dispatch, so even OPTIONS redirects.
ACCEPTED_CELLS: tuple[tuple[ObjectScopedRoute, str], ...] = tuple(
    (route, verb) for route in OBJECT_SCOPED_ROUTES for verb in route.accepted_verbs
)

# The subset that actually reaches `get_queryset`, and therefore the subset the 404 contract
# applies to. Derived from `ACCEPTED_CELLS` rather than listed, so a new accepted verb joins
# this sweep by default and has to be deliberately excluded to escape it.
OBJECT_LOOKUP_CELLS: tuple[tuple[ObjectScopedRoute, str], ...] = tuple(
    (route, verb) for route, verb in ACCEPTED_CELLS if verb != METADATA_VERB
)

# The routes that answer OPTIONS at all. `gpx:upload` is absent: it narrows to POST, so its
# OPTIONS is a 405 and belongs to the rejected sweep instead.
METADATA_ROUTES: tuple[ObjectScopedRoute, ...] = tuple(
    route for route in OBJECT_SCOPED_ROUTES if METADATA_VERB in route.accepted_verbs
)

# (route, verb) for every verb a route refuses. The complement of the above within
# `PROBED_VERBS`, computed rather than listed, so narrowing a view's `http_method_names`
# moves a cell from one sweep to the other instead of leaving the new verb untested.
REJECTED_CELLS: tuple[tuple[ObjectScopedRoute, str], ...] = tuple(
    (route, verb)
    for route in OBJECT_SCOPED_ROUTES
    for verb in PROBED_VERBS
    if verb not in route.accepted_verbs
)


def _cell_id(value: object) -> str:
    """Render one parameter into a test id, so `-v` names the route and verb that broke.

    Without this a dataclass parameter shows as `route0` and a failure means opening the
    file to find out which of the five routes it was.
    """
    if isinstance(value, ObjectScopedRoute):
        return value.name
    return str(value)


def _primary_verb(route: ObjectScopedRoute) -> str:
    """The verb a route is reached by in normal use — the first of its accepted set.

    `accepted_verbs` is written primary-first for exactly this: `get` for the three pages
    and the download, `post` for the upload, whose URL is nothing but a form target.
    """
    return route.accepted_verbs[0]


def _route_named(name: str) -> ObjectScopedRoute:
    """Look one descriptor up by route name, for the cells that are not a full sweep."""
    matches = [route for route in OBJECT_SCOPED_ROUTES if route.name == name]
    assert len(matches) == 1, f"{name!r} is not a single row of OBJECT_SCOPED_ROUTES"
    return matches[0]


def _build_target(
    route: ObjectScopedRoute, owner: User, make_stored_track: StoredTrackFactory
) -> TargetObjects:
    """Create the objects a cell aims at, owned by somebody the requesting client is not.

    Real bytes are written only for the track-pk route, because only its probe reads them.
    The other four get a bare trip — the cheaper setup, and the matrix pays this cost once
    per cell across roughly forty of them.
    """
    trip = Trip.objects.create(name=TARGET_TRIP_NAME, date=TARGET_TRIP_DATE, owner=owner)
    if route.pk_object == "trip":
        return TargetObjects(trip=trip)
    track = make_stored_track(trip, TARGET_TRACK_CONTENT)
    return TargetObjects(trip=trip, track=track, track_content=TARGET_TRACK_CONTENT)


def _url_for(route: ObjectScopedRoute, target: TargetObjects) -> str:
    """Reverse the route against whichever object's pk it takes."""
    if route.pk_object == "track":
        assert target.track is not None, f"{route.name} takes a track pk but none was built"
        return reverse(route.name, kwargs={"pk": target.track.pk})
    return reverse(route.name, kwargs={"pk": target.trip.pk})


def _url_for_a_pk_that_does_not_exist(route: ObjectScopedRoute, target: TargetObjects) -> str:
    """The same route, aimed at nothing — the control the OPTIONS cell compares against.

    Offset from the target's own pk rather than a bare literal, so the two URLs differ only
    in the digit and the comparison cannot be spoiled by a fixture that happened to create
    the number this reached for.
    """
    pk = target.track.pk if route.pk_object == "track" and target.track else target.trip.pk
    return reverse(route.name, kwargs={"pk": pk + 10_000})


def _issue(
    client: Client, verb: str, url: str, data: dict[str, Any] | None = None
) -> HttpResponseBase:
    """Send `verb` at `url` through the test client.

    Dispatched by name rather than through `Client.generic`, so each verb goes through the
    same client method a hand-written test would call — `post` still encodes a form body,
    `options` still supplies the content type Django's own helper does.
    """
    send = getattr(client, verb)
    return cast(HttpResponseBase, send(url) if data is None else send(url, data))


def test_the_matrix_is_parametrized_from_the_whole_inventory() -> None:
    """Every declared route reaches both sweeps — none is silently absent from the cells.

    The guard above proves the inventory matches the URLconf; this proves the *matrix*
    matches the inventory. Between them, a route cannot exist without being swept: a row
    added to `OBJECT_SCOPED_ROUTES` with an empty `accepted_verbs`, or a comprehension
    later narrowed with a filter, would otherwise leave a route classified but unprobed.
    """
    declared = {route.name for route in OBJECT_SCOPED_ROUTES}

    assert {route.name for route, _ in ACCEPTED_CELLS} == declared, (
        f"the accepted-verb sweep covers {sorted({r.name for r, _ in ACCEPTED_CELLS})} but the "
        f"inventory declares {sorted(declared)} — a classified route has no cell proving it "
        f"refuses a non-owner"
    )
    assert {route.name for route, _ in REJECTED_CELLS} == declared, (
        f"the rejected-verb sweep covers {sorted({r.name for r, _ in REJECTED_CELLS})} but the "
        f"inventory declares {sorted(declared)} — a route accepting every probed verb would "
        f"land here, and that is itself worth reading as a failure"
    )
    assert len(ACCEPTED_CELLS) == sum(len(r.accepted_verbs) for r in OBJECT_SCOPED_ROUTES)
    assert len(ACCEPTED_CELLS) + len(REJECTED_CELLS) == len(OBJECT_SCOPED_ROUTES) * len(
        PROBED_VERBS
    ), "every route must be swept with every probed verb, in one sweep or the other"
    assert len(OBJECT_LOOKUP_CELLS) + len(METADATA_ROUTES) == len(ACCEPTED_CELLS), (
        "every accepted verb is swept either as an object lookup (404 for a non-owner) or as "
        "an OPTIONS metadata cell — a verb in neither would accept a request unexamined"
    )
    assert {route.name for route, _ in OBJECT_LOOKUP_CELLS} == declared, (
        f"{sorted(declared - {r.name for r, _ in OBJECT_LOOKUP_CELLS})} accept OPTIONS and "
        f"nothing else, so no cell proves they refuse a non-owner an actual object"
    )


@pytest.mark.django_db
@pytest.mark.parametrize(("route", "verb"), OBJECT_LOOKUP_CELLS, ids=_cell_id)
def test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object(
    route: ObjectScopedRoute,
    verb: str,
    auth_client: Client,
    other_rider: User,
    make_stored_track: StoredTrackFactory,
) -> None:
    """404 — never 403 — from a logged-in rider with no claim to the object.

    Produced by the owner-scoped queryset, which is why the answer is indistinguishable
    from a pk that does not exist. The per-behavior test files cover the GET and POST
    corners of this; what only a sweep can prove is that `head` is scoped too — a verb
    `View.setup` aliases onto `get` without any view here writing a handler for it, and
    one no test in the suite had ever issued.

    `OPTIONS` is excluded and has its own cell below: `View.options` answers from the
    class's verb list and never reaches `get_queryset`, so demanding 404 of it would be
    asserting a contract the framework does not offer and does not need to.

    The probe is the half with the signal: a bare `== 404` passes against a view that
    read, wrote or deleted the object and refused afterwards.
    """
    target = _build_target(route, other_rider, make_stored_track)
    url = _url_for(route, target)

    response = _issue(auth_client, verb, url)

    assert response.status_code == 404, (
        f"{verb.upper()} {url} answered {response.status_code} to a rider who does not own the "
        f"object — anything but 404 here is a data-isolation failure, and a 403 in particular "
        f"confirms the pk exists"
    )
    route.probe(target, response)


@pytest.mark.django_db
@pytest.mark.parametrize("route", METADATA_ROUTES, ids=_cell_id)
def test_options_answers_metadata_only_and_reveals_no_pk(
    route: ObjectScopedRoute,
    auth_client: Client,
    other_rider: User,
    make_stored_track: StoredTrackFactory,
) -> None:
    """200 to a non-owner, and that is the correct contract — do not "fix" this to 404.

    `View.options` builds its response from `self._allowed_methods()`, which reads the
    class's verb list. `dispatch` routes to it the same way it routes to `get`, so it runs
    *before* `get_queryset` and the object is never fetched. There is consequently nothing
    for an owner-scoped queryset to scope, and answering 404 would require the view to
    consult ownership purely so it could refuse a request that carries no data either way.

    So the guarantee this cell asserts is not a refusal — it is a **non-disclosure**, and
    it is asserted by comparison rather than by inspection: the same request against a pk
    that does not exist must produce the same status, the same `Allow` header and the same
    (empty) body. Identical responses cannot tell an attacker enumerating pks which ones
    are real, which is the whole of what the 404 buys on the other verbs.

    The empty-body leg is what would fail first if a future view overrode `options` to
    render something about the object.
    """
    target = _build_target(route, other_rider, make_stored_track)
    real_url = _url_for(route, target)
    absent_url = _url_for_a_pk_that_does_not_exist(route, target)

    response = _issue(auth_client, METADATA_VERB, real_url)
    control = _issue(auth_client, METADATA_VERB, absent_url)

    assert response.status_code == 200, (
        f"OPTIONS {real_url} answered {response.status_code} — this verb is expected to be "
        f"handled by `View.options` without an object lookup, so a different status means the "
        f"view now does something with the pk and this cell no longer describes it"
    )
    assert _body(response) == b"", (
        f"OPTIONS {real_url} returned a body — `View.options` sends none, so something is now "
        f"rendering content for a rider who does not own the object"
    )
    assert (response.status_code, response.headers.get("Allow"), _body(response)) == (
        control.status_code,
        control.headers.get("Allow"),
        _body(control),
    ), (
        f"OPTIONS {real_url} and OPTIONS {absent_url} answered differently, so the response "
        f"reveals whether a pk exists — a rider can enumerate another rider's objects without "
        f"ever reading one"
    )
    assert response.headers.get("Allow"), (
        f"OPTIONS {real_url} carries no Allow header, so the 200 says nothing at all — the "
        f"comparison above would then pass on two equally empty responses"
    )
    route.probe(target, response)


@pytest.mark.django_db
@pytest.mark.parametrize(("route", "verb"), ACCEPTED_CELLS, ids=_cell_id)
def test_an_anonymous_visitor_is_sent_to_login_on_every_verb_a_route_accepts(
    route: ObjectScopedRoute,
    verb: str,
    client: Client,
    rider: User,
    make_stored_track: StoredTrackFactory,
) -> None:
    """302 to the login page with an exact `?next=`, from a different mechanism entirely.

    `LoginRequiredMixin.dispatch` produces this, not the queryset — so this sweep and the
    404 sweep above fail independently: an ownership regression is invisible here, and a
    mixin dropped from a view's bases is invisible there. The target is owned by the
    *first* rider precisely because ownership is irrelevant on this leg; nobody is logged
    in, so there is no owner to compare against.

    `?next=` is asserted exactly, not merely for the redirect: a login round-trip that
    loses it drops the rider on the trip list instead of the page they asked for.
    """
    target = _build_target(route, rider, make_stored_track)
    url = _url_for(route, target)

    response = _issue(client, verb, url)

    assert response.status_code == 302, (
        f"{verb.upper()} {url} answered {response.status_code} to an anonymous visitor rather "
        f"than redirecting to login — the PRD's 'unauthenticated users cannot view any trip' "
        f"no longer holds on this verb"
    )
    assert response.headers["Location"] == f"{reverse('login')}?next={url}", (
        f"the login redirect for {verb.upper()} {url} points at "
        f"{response.headers['Location']!r} — signing in will not return the rider to the page "
        f"they asked for"
    )
    route.probe(target, response)


@pytest.mark.django_db
@pytest.mark.parametrize(("route", "verb"), REJECTED_CELLS, ids=_cell_id)
def test_a_second_rider_gets_405_on_a_verb_the_route_does_not_accept(
    route: ObjectScopedRoute,
    verb: str,
    auth_client: Client,
    other_rider: User,
    make_stored_track: StoredTrackFactory,
) -> None:
    """405, and 405 is correct here — do not "fix" this to 404.

    `View.dispatch` resolves a handler by method name *before* `get_queryset` ever runs,
    so the 405 is produced without the object being looked up at all: the response is
    byte-identical for a real pk and a nonexistent one, and therefore discloses nothing.
    Asserting 404 instead would demand the view consult ownership first, which is strictly
    more work for strictly less safety.

    What this sweep protects is the narrowing itself, which is a security control on two
    of these views and only ever tested for the owner. `trips/views.py:151` left at the
    default lets a raw `DELETE` run `DeletionMixin.delete()` straight to
    `self.object.delete()` — destroying the trip and, through the `post_delete` receiver,
    its GPX file, without the confirmation page ever rendering. `trips/views.py:120`
    left at the default lets `PUT` re-enter `post()` against an empty `request.POST`.
    """
    target = _build_target(route, other_rider, make_stored_track)
    url = _url_for(route, target)

    response = _issue(auth_client, verb, url)

    assert response.status_code == 405, (
        f"{verb.upper()} {url} answered {response.status_code} rather than 405 — the view now "
        f"has a handler for a verb it is not meant to answer, which for trips:delete means a "
        f"raw DELETE bypasses the confirmation page entirely"
    )
    route.probe(target, response)


@pytest.mark.django_db
@pytest.mark.parametrize("route", OBJECT_SCOPED_ROUTES, ids=_cell_id)
def test_the_first_riders_objects_are_equally_unreachable_from_the_second(
    route: ObjectScopedRoute,
    other_auth_client: Client,
    rider: User,
    make_stored_track: StoredTrackFactory,
) -> None:
    """The same refusal with the roles swapped, on each route's primary verb.

    Until `other_auth_client` existed, `other_rider` was only ever the *owner* of data
    somebody else asked for, so every cross-user assertion in the suite ran in one
    direction and took the idiom's symmetry on trust. It is symmetric by construction —
    `filter(owner=request.user)` has no privileged side — but that was an assumption, and
    this is the assertion. Deliberately not a second full verb sweep: the verb dimension
    is already covered above and cannot interact with which rider is asking.
    """
    target = _build_target(route, rider, make_stored_track)
    url = _url_for(route, target)

    response = _issue(other_auth_client, _primary_verb(route), url)

    assert response.status_code == 404, (
        f"{_primary_verb(route).upper()} {url} answered {response.status_code} to the second "
        f"rider — isolation holds in one direction only, so the owner-scoped queryset is not "
        f"the thing deciding it"
    )
    route.probe(target, response)


@pytest.mark.django_db
def test_an_invalid_edit_submission_against_a_foreign_trip_is_not_an_existence_oracle(
    auth_client: Client, other_rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """A 200 form-error page here would confirm the trip exists as loudly as a 403 would.

    The existing edit test posts a *well-formed* body (`tests/trips/test_trip_edit.py:163`),
    which cannot catch the ordering this asserts: a view that binds and validates the form
    before resolving the object re-renders 200 with field errors for a pk the rider does
    not own, and 404s only for a pk that does not exist. The two responses differ, and the
    difference is the disclosure. `UpdateView.post` resolves `self.object` first, which is
    what makes both cases identical — this is the cell that fails if that is ever inverted.
    """
    route = _route_named("trips:edit")
    target = _build_target(route, other_rider, make_stored_track)
    url = _url_for(route, target)

    response = _issue(auth_client, "post", url, {"name": "", "date": "", "description": ""})

    assert response.status_code == 404, (
        f"an invalid POST at {url} answered {response.status_code} — a 200 means the form ran "
        f"before ownership did, and the re-rendered error page tells a rider that somebody "
        f"else's trip exists at this pk"
    )
    route.probe(target, response)


@pytest.mark.django_db
def test_an_invalid_upload_against_a_foreign_trip_is_not_an_existence_oracle(
    auth_client: Client, other_rider: User, make_stored_track: StoredTrackFactory
) -> None:
    """The mirror cell on the route that is already safe, so it is pinned rather than believed.

    `GpxUploadView.post` overrides `post` for precisely this reason — it resolves the trip
    through the owner-scoped queryset before `super().post()` touches the form
    (`gpx/views.py:46-54`). That override is load-bearing and undefended: deleting it
    leaves every other upload test green, because they all post at a trip the rider owns.
    """
    route = _route_named("gpx:upload")
    target = _build_target(route, other_rider, make_stored_track)
    url = _url_for(route, target)

    response = _issue(
        auth_client,
        "post",
        url,
        {"file": SimpleUploadedFile("notes.txt", b"not a gpx file", content_type="text/plain")},
    )

    assert response.status_code == 404, (
        f"an invalid upload at {url} answered {response.status_code} — a 200 re-render of the "
        f"trip detail page confirms that somebody else's trip exists at this pk, whatever the "
        f"file was"
    )
    route.probe(target, response)


# --------------------------------------------------------------------------------------
# Boundary probes: the two refusals no view in this project produces.
# --------------------------------------------------------------------------------------
#
# Everything above is driven by `OBJECT_SCOPED_ROUTES`, because everything above is a route
# this project wrote and can be reversed by name. These two are not. One is the *absence*
# of a route, and the other belongs to `django.contrib.admin`. Neither can appear in the
# inventory, so neither can be swept — which is exactly why they need writing out by hand:
# a guard that only checks the tuple cannot notice a guarantee that lives outside it.

# actor label -> (client fixture, fixture owning the track). Three actors for one URL, and
# the **owner** is the load-bearing one: the guarantee is that nothing serves this prefix at
# all, not that the prefix is owner-scoped. Drop the owner cell and this test keeps passing
# against a media route that had been added and merely happened to be authenticated.
MEDIA_PROBE_ACTORS: dict[str, tuple[str, str]] = {
    "owner": ("auth_client", "rider"),
    "second-rider": ("auth_client", "other_rider"),
    "anonymous": ("client", "rider"),
}

# actor label -> client fixture. `auth_client` is a plain rider: `create_user` leaves
# `is_staff` false, which is the whole population this cell speaks for.
ADMIN_BOUNDARY_ACTORS: dict[str, str] = {
    "non-staff-rider": "auth_client",
    "anonymous": "client",
}


@pytest.mark.django_db
@pytest.mark.parametrize("actor", tuple(MEDIA_PROBE_ACTORS))
def test_no_url_under_media_url_serves_a_stored_track(
    actor: str, request: pytest.FixtureRequest, make_stored_track: StoredTrackFactory
) -> None:
    """Nothing is served from `MEDIA_URL` — asserted as a request, not as a settings value.

    Half of Risk #2 is "downloads their track file", and this project's entire defense on
    that half is that **no route exists** under the media prefix. `gpx:download` is the only
    way to a stored file, and it is `LoginRequiredMixin` plus a `trip__owner` traversal.

    That defense is one line away from gone, in several directions: a
    `urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` added for
    local convenience, a `WHITENOISE_ROOT` pointed at the volume, a platform-level static
    handler mounted ahead of the app. Any of them serves every rider's GPX to anyone holding
    the URL, and WhiteNoise in particular sits *ahead* of `AuthenticationMiddleware`
    (`velo_log/settings.py:66,70`), so what it serves is outside authorization by
    construction — there is no `request.user` yet when it answers.

    Not one existing test would go red: they all go through `gpx:download`. The nearest
    thing is `tests/test_media_storage.py:106-107`, which asserts a *settings value* — true
    of a config that has since been overridden by a route, a middleware or a platform.

    The URL comes from `track.file.url` rather than a literal because `gpx/models.py:8-17`
    discards the user's filename and names the file with `secrets.token_hex(16)`. A
    hardcoded `/media/gpx/1/1/x.gpx` would 404 because no such file exists, which is a pass
    for the wrong reason — and would keep passing after a media route was added.
    """
    client_fixture, owner_fixture = MEDIA_PROBE_ACTORS[actor]
    client = cast(Client, request.getfixturevalue(client_fixture))
    owner = cast(User, request.getfixturevalue(owner_fixture))

    trip = Trip.objects.create(name=TARGET_TRIP_NAME, date=TARGET_TRIP_DATE, owner=owner)
    track = make_stored_track(trip, TARGET_TRACK_CONTENT)
    url = track.file.url

    # Without this the test silently becomes a probe of some unrelated path the moment
    # `MEDIA_URL` changes, and a probe of an unrelated path passes for free.
    assert url.startswith(settings.MEDIA_URL), (
        f"{url!r} does not start with MEDIA_URL ({settings.MEDIA_URL!r}), so this test is no "
        f"longer requesting the prefix it exists to prove is unserved"
    )

    response = client.get(url)

    assert response.status_code == 404, (
        f"{url} answered {response.status_code} to the {actor} — a URL under MEDIA_URL now "
        f"resolves, so every rider's stored track is reachable by anyone holding its URL, "
        f"outside AuthenticationMiddleware and outside the owner-scoped queryset entirely"
    )
    assert TARGET_TRACK_CONTENT not in _body(response), (
        f"{url} returned the stored bytes of a track to the {actor} — the file is being "
        f"served straight off the media volume"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("actor", tuple(ADMIN_BOUNDARY_ACTORS))
def test_the_admin_object_route_refuses_a_visitor_who_is_not_staff(
    actor: str, request: pytest.FixtureRequest, other_rider: User
) -> None:
    """302 to the admin login — and 302 is the contract here, not the 404 above.

    Both `ModelAdmin`s are deliberately unscoped (`trips/admin.py:13-22`,
    `gpx/admin.py:13-29`): any `is_staff` user with model permissions reads every rider's
    data, which is what an admin is for. The isolation guarantee therefore does not say
    "the admin scopes by owner" — it reduces to **no non-staff visitor reaches it at all**,
    and that is the boundary this pins. `test-plan.md` §7 excludes admin as a *product
    surface*; the boundary of a guarantee is not the product surface, which is the same
    reasoning §7 already uses to keep the admin file-replacement path tested under Risk #1.

    Deliberately not asserted: that staff *can* read every user's data. That is admin as a
    product surface, and asserting it here would turn a boundary check into a spec for a
    behavior nobody has decided to keep.

    Why not 404: `AdminSite.admin_view` checks `has_permission` and calls
    `redirect_to_login` — it never reaches a queryset, so there is nothing to scope and no
    404 to produce. A cell copied from the matrix above would assert the wrong contract and
    then get "fixed" by someone making the admin lie about what exists. The `?next=` is
    asserted for the same reason it is on the app's own routes: it carries the real object
    path, which is what a staff member is returned to after signing in.
    """
    client = cast(Client, request.getfixturevalue(ADMIN_BOUNDARY_ACTORS[actor]))
    trip = Trip.objects.create(name=TARGET_TRIP_NAME, date=TARGET_TRIP_DATE, owner=other_rider)
    url = reverse("admin:trips_trip_change", args=[trip.pk])

    response = client.get(url)

    assert response.status_code == 302, (
        f"{url} answered {response.status_code} to the {actor} — a visitor who is not staff "
        f"reached an admin route onto another rider's trip, where nothing scopes by owner"
    )
    assert response.headers["Location"] == f"{reverse('admin:login')}?next={url}", (
        f"the admin refusal for the {actor} points at {response.headers['Location']!r} rather "
        f"than the admin login carrying {url} — either the refusal is no longer the login "
        f"redirect, or it has stopped preserving which object was asked for"
    )
    assert TARGET_TRIP_NAME.encode() not in _body(response), (
        f"the refusal shown to the {actor} names the trip it refused, which tells a visitor "
        f"with no admin access that this pk belongs to a real trip"
    )
