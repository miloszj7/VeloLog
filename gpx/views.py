from functools import partial
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import CreateView

from gpx.forms import GpxUploadForm
from gpx.models import GpxTrack
from trips.models import Trip

if TYPE_CHECKING:
    _GpxUploadViewBase = CreateView[GpxTrack, GpxUploadForm]
    _SuccessMessageMixinBase = SuccessMessageMixin[GpxUploadForm]
else:
    _GpxUploadViewBase = CreateView
    _SuccessMessageMixinBase = SuccessMessageMixin


class GpxUploadView(LoginRequiredMixin, _SuccessMessageMixinBase, _GpxUploadViewBase):
    """Attaches a GPX track to one of the requesting user's own trips, replacing any existing one.

    The view lives in `gpx/` but renders a `trips/` template. That cross-app reference is
    deliberate: the model, parsing and validation belong to `gpx/`, while the page the
    user is looking at is a trip's detail page. Re-rendering it here is what puts the
    error next to the form the user just submitted.
    """

    form_class = GpxUploadForm
    template_name = "trips/trip_detail.html"
    success_message = "Route uploaded."
    # POST-only: the form is served from the trip detail page, and this URL is nothing
    # but its target. A GET here would render a second, unlinked copy of that page.
    http_method_names = ["post"]

    trip: Trip

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Resolve the target trip before any of the upload is looked at.

        Doing it here rather than in `form_valid` is what makes a POST at another user's
        trip 404 whatever the file was — otherwise an invalid file against a trip the
        user does not own would render a 200 page and confirm the trip exists.
        """
        self.trip = self.get_trip()
        return super().post(request, *args, **kwargs)

    def get_trip(self) -> Trip:
        """Resolve the trip through an owner-scoped queryset, so another user's pk 404s.

        Scoping the queryset rather than checking ownership after fetching is the whole
        of this project's authorization story — `TripDetailView.get_queryset` does the
        same, and gives the same 404-not-403 answer.
        """
        return get_object_or_404(
            Trip.objects.filter(owner=cast(User, self.request.user)), pk=self.kwargs["pk"]
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Supply what `trips/trip_detail.html` needs when re-rendering with errors."""
        context = super().get_context_data(**kwargs)
        context["trip"] = self.trip
        context["track"] = self.trip.tracks.first()
        return context

    def get_success_url(self) -> str:
        return self.trip.get_absolute_url()

    def form_valid(self, form: GpxUploadForm) -> HttpResponse:
        """Persist the new track, then retire the one it supersedes.

        The ordering is load-bearing on both axes:

        * The new row and its file are saved **first**. The reverse order loses both if
          the new save fails.
        * The superseded *file* is deleted on commit, never inside the block. Storage
          deletes do not participate in the transaction, so a delete performed inside
          `atomic()` is already gone if the block later raises — the database then rolls
          the old row back into existence pointing at a file that no longer exists, and
          the detail page renders a track whose download 404s. That is precisely the
          silent-failure state the mitigation exists to prevent.
        """
        # The parsed route is already on the instance — `GpxUploadForm.clean_file` puts
        # it there. Ownership is the one thing the form cannot know.
        form.instance.trip = self.trip

        superseded = list(self.trip.tracks.all())
        with transaction.atomic():
            # Saves the row and writes the file, adds the success message, and returns
            # the redirect to `get_success_url`.
            response = super().form_valid(form)
            self.trip.tracks.exclude(pk=form.instance.pk).delete()
            for old in superseded:
                transaction.on_commit(partial(old.file.delete, save=False))
        return response
