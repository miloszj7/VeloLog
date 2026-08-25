from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

# `gpx` already imports `trips` (its model points at `Trip`), so this line makes the
# dependency mutual. Accepted rather than avoided: the trip detail page is where a route
# is uploaded and viewed, so the two apps describe one page between them. There is no
# import cycle — `trips.models` imports nothing from `gpx`, and that is the line to keep
# unbroken; a model-level import in either direction is what would turn this into one.
from gpx.forms import GpxUploadForm
from trips.forms import TripForm
from trips.models import Trip

if TYPE_CHECKING:
    _TripListViewBase = ListView[Trip]
    _TripDetailViewBase = DetailView[Trip]
    _TripCreateViewBase = CreateView[Trip, TripForm]
    _SuccessMessageMixinBase = SuccessMessageMixin[TripForm]
else:
    _TripListViewBase = ListView
    _TripDetailViewBase = DetailView
    _TripCreateViewBase = CreateView
    _SuccessMessageMixinBase = SuccessMessageMixin


class TripListView(LoginRequiredMixin, _TripListViewBase):
    """Lists the requesting user's own trips."""

    def get_queryset(self) -> QuerySet[Trip]:
        """Restrict the list to trips owned by the requesting user."""
        return Trip.objects.filter(owner=cast(User, self.request.user))


class TripCreateView(LoginRequiredMixin, _SuccessMessageMixinBase, _TripCreateViewBase):
    """Creates a trip owned by the requesting user."""

    form_class = TripForm
    template_name = "trips/trip_form.html"
    success_url = reverse_lazy("trips:list")
    success_message = "Trip saved."

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
        """Expose the trip's current track, or `None` when nothing has been uploaded.

        The unbound upload form is supplied here too. The page hosts a form it does not
        own, so this GET path and `GpxUploadView`'s re-render path have to present the
        same template with the same context keys — one of them bound, one of them not.
        """
        context = super().get_context_data(**kwargs)
        context["track"] = self.object.tracks.first()
        context["form"] = GpxUploadForm()
        return context
