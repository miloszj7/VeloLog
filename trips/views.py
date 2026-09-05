from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Min, QuerySet
from django.forms import Form
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

# `gpx` already imports `trips` (its model points at `Trip`), so this line makes the
# dependency mutual. Accepted rather than avoided: the trip detail page is where a route
# is uploaded and viewed, so the two apps describe one page between them. There is no
# import cycle — `trips.models` imports nothing from `gpx`, and that is the line to keep
# unbroken; a model-level import in either direction is what would turn this into one.
from gpx.forms import GpxUploadForm
from gpx.map_config import build_map_config
from gpx.models import GpxTrack
from gpx.stages import build_stages, chronology_is_established, trip_span
from gpx.statistics import build_whole_trip_stats
from trips.dates import span_date_diverges, trip_date_diverges
from trips.forms import TripForm
from trips.models import Trip

if TYPE_CHECKING:
    _TripListViewBase = ListView[Trip]
    _TripDetailViewBase = DetailView[Trip]
    _TripCreateViewBase = CreateView[Trip, TripForm]
    _TripUpdateViewBase = UpdateView[Trip, TripForm]
    # Two parameters, and the second is `django.forms.Form` rather than `TripForm`:
    # `BaseDeleteView` posts an empty `Form` it declares itself. The same reason forces a
    # second `SuccessMessageMixin` alias below — the mixin is parameterized by the form,
    # so `_SuccessMessageMixinBase` above (bound to `TripForm`) cannot be reused here.
    _TripDeleteViewBase = DeleteView[Trip, Form]
    _SuccessMessageMixinBase = SuccessMessageMixin[TripForm]
    _DeleteSuccessMessageMixinBase = SuccessMessageMixin[Form]
else:
    _TripListViewBase = ListView
    _TripDetailViewBase = DetailView
    _TripCreateViewBase = CreateView
    _TripUpdateViewBase = UpdateView
    _TripDeleteViewBase = DeleteView
    _SuccessMessageMixinBase = SuccessMessageMixin
    _DeleteSuccessMessageMixinBase = SuccessMessageMixin


class TripListView(LoginRequiredMixin, _TripListViewBase):
    """Lists the requesting user's own trips."""

    def get_queryset(self) -> QuerySet[Trip]:
        """Restrict the list to trips owned by the requesting user."""
        return Trip.objects.filter(owner=cast(User, self.request.user))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Flag which listed trips diverge, in one extra aggregate query.

        Not an `.annotate()` on the `Trip` queryset itself: `get_queryset`'s declared
        `-> QuerySet[Trip]:` return type would erase any annotation's django-stubs
        typing the moment it's returned, and `Trip` has no `date_diverges` field for an
        ad hoc instance attribute to satisfy under `mypy --strict`. A separate small
        aggregate query, reduced to a plain `set[int]` of pks, sidesteps both problems
        and costs one query for the whole list, not one per row.

        Requires the same full-chronology gate as `trip_span`/`chronology_is_established`
        (`gpx/stages.py`) — every stage timed, not merely the earliest one — so this
        indicator and the detail page's "Logged as ..." note agree on which trips
        diverge. `total == timed` (both from `Count`, which ignores NULLs) is that gate
        expressed as an aggregate rather than a Python loop over materialized tracks.
        """
        context = super().get_context_data(**kwargs)
        trips = context["object_list"]
        aggregates = (
            GpxTrack.objects.filter(trip__in=trips)
            .values("trip_id")
            .annotate(total=Count("id"), timed=Count("started_at"), earliest=Min("started_at"))
        )
        earliest_by_trip_id = {
            row["trip_id"]: row["earliest"]
            for row in aggregates
            if row["total"] > 0 and row["total"] == row["timed"]
        }
        context["diverging_trip_ids"] = {
            trip.pk
            for trip in trips
            if (earliest := earliest_by_trip_id.get(trip.pk)) is not None
            and trip_date_diverges(trip.date, earliest)
        }
        return context


class TripCreateView(LoginRequiredMixin, _SuccessMessageMixinBase, _TripCreateViewBase):
    """Creates a trip owned by the requesting user."""

    form_class = TripForm
    template_name = "trips/trip_form.html"
    success_url = reverse_lazy("trips:list")
    success_message = "Trip saved."
    # The same narrowing, and the same list, as `TripUpdateView` below — the two views
    # render one template through one form class, so a verb one of them refuses and the
    # other answers with a field-error re-render is a difference with no reason behind it.
    http_method_names = ["get", "post", "head", "options"]

    def form_valid(self, form: TripForm) -> HttpResponse:
        """Assign the requesting user as owner before saving the trip."""
        form.instance.owner = cast(User, self.request.user)
        return super().form_valid(form)


class TripDetailView(LoginRequiredMixin, _TripDetailViewBase):
    """Shows one of the requesting user's own trips, with its track if one exists."""

    def get_queryset(self) -> QuerySet[Trip]:
        """Restrict the lookup to trips owned by the requesting user.

        Scoping here — rather than checking ownership after fetching — is what makes
        another user's trip 404 instead of 403, so a pk that exists is indistinguishable
        from one that does not. The owner-scoped queryset is the project's entire
        authorization story; `TripListView.get_queryset` above does the same.
        """
        return Trip.objects.filter(owner=cast(User, self.request.user))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Expose the trip's stages, in ride order, or an empty tuple when none exist.

        The unbound upload form is supplied here too. The page hosts a form it does not
        own, so this GET path and `GpxUploadView`'s re-render path have to present the
        same template with the same context keys — one of them bound, one of them not.
        The map blob is on that list, and so are `chronology_established`,
        `trip_span`, `whole_trip_stats`, and `date_diverges`: any key supplied here and
        missed there renders a wrong branch over healthy data — "route could not be
        displayed" for the first, a false chronology claim for the second, a multi-day
        tour whose header silently collapses back to its start date the moment an
        upload is rejected for the third, stale or missing whole-trip totals for the
        fourth, and a divergence note that silently disappears on a rejected upload for
        the fifth.
        """
        context = super().get_context_data(**kwargs)
        stages = build_stages(self.object)
        tracks = [stage.track for stage in stages]
        span = trip_span(tracks)
        context["stages"] = stages
        context["map_config"] = build_map_config(stages)
        context["chronology_established"] = chronology_is_established(tracks)
        context["trip_span"] = span
        context["whole_trip_stats"] = build_whole_trip_stats(tracks)
        context["date_diverges"] = span_date_diverges(self.object.date, span)
        context["form"] = GpxUploadForm()
        return context


class TripUpdateView(LoginRequiredMixin, _SuccessMessageMixinBase, _TripUpdateViewBase):
    """Edits one of the requesting user's own trips."""

    form_class = TripForm
    # Named rather than left to `UpdateView`'s default, which resolves to this same
    # template anyway. `trips/trip_form.html` was written for the create flow and now
    # branches on `form.instance.pk`; saying which template this view renders is what
    # keeps that shared ownership visible to the next reader.
    template_name = "trips/trip_form.html"
    success_message = "Trip updated."
    # No write verbs beyond POST. Left at the default, `ProcessFormView.put` re-enters
    # `post()` against an empty `request.POST`, so a `PUT` would 200-re-render with every
    # field in error instead of returning 405. `GpxUploadView` narrows the same way.
    #
    # `head` and `options` stay in the list because this view serves a page: `View.setup`
    # aliases `head` to `get`, and dropping them would make these two URLs the only pages
    # in the app that refuse a HEAD an authenticated client is entitled to.
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self) -> QuerySet[Trip]:
        """Restrict the lookup to trips owned by the requesting user.

        The same body and the same reason as `TripDetailView.get_queryset` above: another
        user's pk 404s rather than 403s, for the write verbs as much as the read one.
        """
        return Trip.objects.filter(owner=cast(User, self.request.user))


class TripDeleteView(LoginRequiredMixin, _DeleteSuccessMessageMixinBase, _TripDeleteViewBase):
    """Deletes one of the requesting user's own trips, asking on GET and doing on POST."""

    model = Trip
    # Named rather than left to `template_name_suffix = "_confirm_delete"`, for the same
    # reason `TripUpdateView` names its own: which template a view renders should be
    # readable here, not reconstructed from a naming rule.
    template_name = "trips/trip_confirm_delete.html"
    success_url = reverse_lazy("trips:list")
    # Static, not a `%(name)s` template. `BaseDeleteView` posts an empty `Form`, so
    # `get_success_message` is handed `{}` and any interpolation placeholder raises.
    success_message = "Trip deleted."
    # GET and POST only, and load-bearing rather than stylistic here. Left at the default,
    # `DeletionMixin.delete()` stays reachable — `View.dispatch` resolves a handler by
    # method name, so a raw HTTP `DELETE` would run straight through `get_object()` to
    # `self.object.delete()`, destroying the trip and (via the `post_delete` receiver) its
    # GPX file without ever rendering the confirmation page. That page is the only guard
    # the detail-page Delete *link* relies on, so narrowing here is what makes the link
    # safe to be a link. `head` and `options` are kept for the reason `TripUpdateView`
    # gives: this view serves a page, and only `delete`/`put`/`patch` are the point.
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self) -> QuerySet[Trip]:
        """Restrict the lookup to trips owned by the requesting user.

        The same body and the same reason as `TripDetailView.get_queryset` above. This is
        the whole authorization story for delete too: `BaseDeleteView.post` sets
        `self.object = self.get_object()` before it builds the form, so a foreign pk 404s
        on POST as well as on GET. The resolve-the-object-before-the-form override
        `GpxUploadView.post` needs is deliberately *not* repeated here — the framework
        already does it in the right order.
        """
        return Trip.objects.filter(owner=cast(User, self.request.user))
