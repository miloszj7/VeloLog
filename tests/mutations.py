"""Named mutation shapes proving the suite bites — the automated form of test-plan.md §6.2.

A shape is a claim: breaking *this* production behavior makes *that* guard test fail, for a
reason distinctive enough to tell "the guard's own assertion tripped" apart from "the
mutation broke collection" or "nothing failed at all". `tests/test_suite_bites.py` is what
proves each claim by running the guard node in a subprocess with the shape applied and
reading the result; a shape whose guard stays green is a broken shape and the harness
failing on it is correct behavior.

This module only *declares* the shapes — importing it applies nothing. `tests/conftest.py`
is what applies the shape named by the `VELOLOG_MUTATION` environment variable, and only for
the session that variable is set on.

**Patch the name where it is used, not where it is defined.** `trips/views.py` does
`from gpx.availability import track_file_is_available`, so the live reference the view calls
is `trips.views.track_file_is_available`, not `gpx.availability.track_file_is_available`.
`gpx.forms.MAX_GPX_FILE_BYTES` is the same shape: it is imported by value from
`gpx.constants`, so `gpx.constants.MAX_GPX_FILE_BYTES` is not the name the form reads. This is
the convention every shape below follows — it is the name the code actually reads, and the
one a reader expects — not a guaranteed false green: patching the defining module instead was
tried once, deliberately, against `track_file_is_available`, and the harness still caught it,
because Django's lazy view import means the patch on the defining module propagates through to
the view's own reference anyway (see `context/foundation/test-plan.md` §6.7 Phase 5).
"""

import dataclasses
from collections.abc import Callable
from typing import Any


@dataclasses.dataclass(frozen=True)
class MutationShape:
    """One registered mutation: what to patch, what to patch it to, and what must go red.

    `attribute` may be dotted (`"TripDetailView.get_queryset"`) to reach a class attribute
    inside `module_path` — `apply` below resolves it one segment at a time so a nested
    target needs no special case.
    """

    name: str
    risk: str
    module_path: str
    attribute: str
    replacement: Callable[[], Any]
    guard_node_id: str
    fragment: str


def _unscoped_trip_detail_queryset() -> Callable[[Any], Any]:
    # Deferred import: this factory only runs once Django is configured (inside the
    # session-scoped conftest fixture, or the subprocess the harness spawns), never at
    # module import time — importing `trips.models` before `django.setup()` has run
    # would raise `AppRegistryNotReady`.
    from trips.models import Trip

    def get_queryset(self: Any) -> Any:
        return Trip.objects.all()

    return get_queryset


def _no_op_file_discard() -> Callable[..., None]:
    def discard_file_by_key(track_pk: int, storage_key: str, storage: Any) -> None:
        return None

    return discard_file_by_key


def _file_always_available() -> Callable[[Any], bool]:
    def track_file_is_available(track: Any) -> bool:
        return True

    return track_file_is_available


def _no_upload_size_cap() -> int:
    # Above any file the suite's fixtures build, including the deliberately oversized one
    # in `test_a_file_over_the_size_cap_is_rejected_with_a_visible_message`.
    return 2**40


def _media_guard_always_clean() -> Callable[[], None]:
    def media_root_misconfiguration() -> None:
        return None

    return media_root_misconfiguration


def _upload_replaces_instead_of_adding() -> Callable[[Any, Any], Any]:
    # Deferred import for the reason `_unscoped_trip_detail_queryset` gives above: this
    # factory only runs once Django is configured.
    def form_valid(self: Any, form: Any) -> Any:
        from django.db import transaction

        from gpx.views import GpxUploadView

        form.instance.trip = self.trip
        with transaction.atomic():
            # The read-then-delete this class's `form_valid` used to perform under
            # replace semantics — reinstated here only to prove the guard test below
            # goes red if it ever comes back for real.
            superseded = list(self.trip.tracks.select_for_update())
            response = super(GpxUploadView, self).form_valid(form)
            self.trip.tracks.filter(pk__in=[track.pk for track in superseded]).delete()
        return response

    return form_valid


# (name, risk, patch target, replacement factory, guard node id, discriminating fragment).
# See tests/test_suite_bites.py::test_every_risk_area_has_a_shape_and_every_guard_node_resolves
# for the asserted claim that every risk area named here actually has coverage, and that
# every guard node id below resolves to a real test.
MUTATION_SHAPES: tuple[MutationShape, ...] = (
    MutationShape(
        name="unscoped_trip_detail_queryset",
        risk="#2",
        # `TripDetailView.get_queryset` is defined in trips/views.py — no re-export trap
        # here, but it is a *class* attribute, so `attribute` carries the dotted path
        # `apply` below walks to reach it.
        module_path="trips.views",
        attribute="TripDetailView.get_queryset",
        replacement=_unscoped_trip_detail_queryset,
        # Narrowed to the single cell the mutation actually exercises (`trips:detail`'s
        # primary verb, `get`) rather than the whole parametrized matrix — an unmutated
        # cell for an unrelated route (e.g. `gpx:download`) failing for its own reason
        # would otherwise satisfy `failed >= 1` and the shared fragment below without the
        # `trips:detail` cell the mutation targets ever going red.
        guard_node_id=(
            "tests/test_ownership_matrix.py::"
            "test_a_second_rider_is_refused_on_every_verb_that_reaches_the_object"
            "[trips:detail-get]"
        ),
        fragment="confirms the pk exists",
    ),
    MutationShape(
        name="no_op_file_discard",
        risk="#1",
        # Defined and used in the same module — `gpx/signals.py` resolves the name as a
        # module global inside `partial(...)` at receiver-call time, so patching it here
        # is patching the exact reference the receiver reads.
        module_path="gpx.signals",
        attribute="discard_file_by_key",
        replacement=_no_op_file_discard,
        guard_node_id=(
            "tests/gpx/test_gpx_signals.py::"
            "test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded"
        ),
        fragment="assert not default_storage.exists(name)",
    ),
    MutationShape(
        name="file_always_available",
        risk="#3",
        # `gpx/stages.py` does `from gpx.availability import track_file_is_available`, and
        # `build_stages` is the only caller left that reads it — `trips/views.py` and
        # `gpx/views.py` both went through `gpx.stages.build_stages` once it started
        # owning this call, so the view's own module no longer holds a reference at all.
        # Patching `gpx.availability.track_file_is_available` would leave `build_stages`
        # untouched, the same re-export trap this shape has always guarded against, just
        # at its new location.
        module_path="gpx.stages",
        attribute="track_file_is_available",
        replacement=_file_always_available,
        guard_node_id=(
            "tests/trips/test_trip_detail.py::"
            "test_a_rider_sees_a_deliberate_marker_when_the_track_file_is_missing"
        ),
        fragment='assert response.context["stages"][0].file_available is False',
    ),
    MutationShape(
        name="no_upload_size_cap",
        risk="#5",
        # `gpx/forms.py` does `from gpx.constants import MAX_GPX_FILE_BYTES` — imported by
        # value, so `gpx.constants.MAX_GPX_FILE_BYTES` is not the name `clean_file` reads.
        module_path="gpx.forms",
        attribute="MAX_GPX_FILE_BYTES",
        replacement=_no_upload_size_cap,
        guard_node_id=(
            "tests/gpx/test_gpx_upload.py::"
            "test_a_file_over_the_size_cap_is_rejected_with_a_visible_message"
        ),
        fragment='assert "larger than 10 MB" in response.content.decode()',
    ),
    MutationShape(
        name="media_guard_always_clean",
        risk="#7",
        # Defined and used in the same module — `_probe_health` calls
        # `media_root_misconfiguration()` as a module global.
        module_path="velo_log.urls",
        attribute="media_root_misconfiguration",
        replacement=_media_guard_always_clean,
        guard_node_id=(
            "tests/test_media_storage.py::"
            "test_healthz_fails_when_media_root_is_inside_base_dir_and_debug_is_false"
        ),
        fragment="assert response.status_code == 500",
    ),
    MutationShape(
        name="upload_replaces_instead_of_adding",
        risk="#1",
        # A class attribute, resolved through the dotted-attribute form
        # `unscoped_trip_detail_queryset` above already established.
        module_path="gpx.views",
        attribute="GpxUploadView.form_valid",
        replacement=_upload_replaces_instead_of_adding,
        guard_node_id=(
            "tests/gpx/test_gpx_upload.py::"
            "test_a_second_upload_adds_a_stage_and_keeps_the_first_file"
        ),
        fragment=(
            "the first stage's row was deleted instead of kept when a second stage " "was added"
        ),
    ),
)


def apply_mutation_shape(shape: MutationShape, monkeypatch: Any) -> None:
    """Patch `shape`'s attribute in place through `monkeypatch`, for the caller's scope.

    `shape.attribute` is resolved one dotted segment at a time starting from the imported
    module, so a plain module attribute (`MAX_GPX_FILE_BYTES`) and a nested class attribute
    (`TripDetailView.get_queryset`) both resolve through the same walk.
    """
    import importlib

    module = importlib.import_module(shape.module_path)
    target: Any = module
    *owner_parts, leaf_name = shape.attribute.split(".")
    for part in owner_parts:
        target = getattr(target, part)
    monkeypatch.setattr(target, leaf_name, shape.replacement())
