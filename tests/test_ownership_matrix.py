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
3. **405 for a verb outside `http_method_names`.** Produced by `View.dispatch`'s method
   lookup, which runs *before* `get_queryset` — so the 405 discloses nothing and is identical
   for a real and a nonexistent pk. Here the narrowing is a security control, not a style
   preference: `trips/views.py:151` left at its default lets a raw `DELETE` destroy a trip
   and its GPX file with no confirmation page.
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
from typing import Literal, cast

from django.http import HttpResponse, HttpResponseBase, StreamingHttpResponse
from django.urls import URLPattern, URLResolver, get_resolver

from gpx.models import GpxTrack
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


def _body(response: HttpResponseBase) -> bytes:
    """Return a response's bytes, draining a streaming response rather than skipping it.

    `gpx:download` answers with a `FileResponse`, so the one response shape that could
    actually leak a foreign rider's track is the streaming one. Reading `.content` on it
    raises; returning `b""` for it would turn the leak probe into a guaranteed pass.

    `streaming_content` is typed as sync-or-async; the cast picks the sync half, which is
    what a `FileResponse` built by `GpxDownloadView` under the sync test client always is.
    """
    if isinstance(response, StreamingHttpResponse):
        return b"".join(cast(Iterator[bytes], response.streaming_content))
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
