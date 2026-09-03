import logging
from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.messages.views import SuccessMessageMixin
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import CreateView, View

from gpx.forms import GpxUploadForm
from gpx.map_config import build_map_config
from gpx.models import GpxTrack
from gpx.stages import build_stages, chronology_is_established
from trips.models import Trip

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    _GpxUploadViewBase = CreateView[GpxTrack, GpxUploadForm]
    _SuccessMessageMixinBase = SuccessMessageMixin[GpxUploadForm]
else:
    _GpxUploadViewBase = CreateView
    _SuccessMessageMixinBase = SuccessMessageMixin


class GpxUploadView(LoginRequiredMixin, _SuccessMessageMixinBase, _GpxUploadViewBase):
    """Attaches a new GPX stage to one of the requesting user's own trips.

    Every upload **adds** a stage; none of them supersede what is already there.
    `gpx/stages.py` is what orders a trip's stages afterwards — chronologically by GPS
    instant where one was recorded, by upload order otherwise — so this view need not
    care what position the new row lands in. No path through this view ever deletes a
    `GpxTrack` row or its file; `gpx/signals.py`'s `post_delete` receiver is the only
    place a stored file is ever removed for that reason, and it stays that way.

    The view lives in `gpx/` but renders a `trips/` template. That cross-app reference is
    deliberate: the model, parsing and validation belong to `gpx/`, while the page the
    user is looking at is a trip's detail page. Re-rendering it here is what puts the
    error next to the form the user just submitted.
    """

    form_class = GpxUploadForm
    template_name = "trips/trip_detail.html"
    success_message = "Stage added."
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
        """Supply what `trips/trip_detail.html` needs when re-rendering with errors.

        Including the map and chronology blobs: this path renders the same page as
        `TripDetailView`, so a rider whose upload was rejected must still see every stage
        they already had, not the template's no-route-to-draw branch and not a false
        "file unavailable" marker over a track whose file is perfectly healthy.
        """
        context = super().get_context_data(**kwargs)
        stages = build_stages(self.trip)
        context["trip"] = self.trip
        context["stages"] = stages
        context["map_config"] = build_map_config(stages)
        context["chronology_established"] = chronology_is_established(
            [stage.track for stage in stages]
        )
        return context

    def get_success_url(self) -> str:
        return self.trip.get_absolute_url()

    def form_valid(self, form: GpxUploadForm) -> HttpResponse:
        """Persist the new stage. Nothing else on the trip is touched.

        This used to open a transaction, read every existing track on the trip, and
        delete that pk set once the new row was saved — replace semantics, not add. That
        block is gone outright, not merely disabled: the multi-statement write it guarded
        no longer exists, so `transaction.atomic()` has nothing left to make atomic. The
        storage-write orphan window it never covered (a process dying between the file
        write and the commit) was never this block's job either — `manage.py
        reconcile_media` is the backstop for that, unchanged.

        Do **not** reinstate a delete here as "cleanup". `gpx/signals.py`'s `post_delete`
        receiver is the only path that ever removes a stage's file, fired once per row a
        delete actually removes — reintroducing a delete in this method would put a
        second, competing path back in, and against a trip that already has a stage that
        path destroys it.
        """
        # The parsed route is already on the instance — `GpxUploadForm.clean_file` puts
        # it there. Ownership is the one thing the form cannot know.
        form.instance.trip = self.trip
        return super().form_valid(form)


class GpxDownloadView(LoginRequiredMixin, View):
    """Serves a track's original file back to its owner, and to nobody else.

    Two separate PRD sentences require this view to exist at all rather than a
    `MEDIA_URL` path: "no user can access another user's trips under any circumstances"
    drives the owner scoping, and "unauthenticated users cannot view any trip" drives
    `LoginRequiredMixin`. A bare media URL breaks both — whitenoise sits ahead of
    `AuthenticationMiddleware` in `MIDDLEWARE`, so anything it serves is outside
    authorization by construction.

    A plain `View` rather than a generic one: there is no form and no object-to-context
    step to inherit, so the `TYPE_CHECKING` base-alias idiom has nothing to work around.
    """

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> FileResponse:
        track = get_object_or_404(
            GpxTrack.objects.filter(trip__owner=cast(User, request.user)), pk=self.kwargs["pk"]
        )
        try:
            stream = track.file.open("rb")
        except OSError:
            # A row whose file is gone is an operational fault, not a bad request, and
            # `DEPLOY.md` already names the ways to get here: a database restored ahead
            # of its media directory, or a deploy that wrote uploads to a directory the
            # next container could not read. Answering 404 matches what this view says
            # about a track that does not exist; the log line is what makes the
            # difference between the two visible to an operator.
            logger.exception(
                "Track file missing from storage",
                extra={"track_id": track.pk, "storage_key": track.file.name},
            )
            raise Http404("The file for this track is not available.") from None
        return FileResponse(
            stream,
            as_attachment=True,
            filename=track.original_filename,
        )
