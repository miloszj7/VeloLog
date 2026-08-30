---
date: 2026-08-30T10:35:30+02:00
researcher: Claude (10x-research)
git_commit: cf74882b3800b472b63a4f836dff299de72381cd
branch: chore/testing-file-lifecycle-storage-consistency
repository: VeloLog
topic: "File lifecycle and storage/row consistency test coverage (Test Plan Phase 2, risks #1 and #3)"
tags: [research, codebase, gpx, signals, storage, reconcile_media, test-plan-phase-2]
status: complete
last_updated: 2026-08-30
last_updated_by: Claude (10x-research)
---

# Research: File lifecycle and storage/row consistency test coverage

**Date**: 2026-08-30T10:35:30+02:00
**Researcher**: Claude (10x-research)
**Git Commit**: cf74882b3800b472b63a4f836dff299de72381cd
**Branch**: chore/testing-file-lifecycle-storage-consistency
**Repository**: VeloLog

## Research Question

Ground rollout Phase 2 of `context/foundation/test-plan.md` ("File lifecycle and
storage/row consistency") against the current codebase: which paths remove or
supersede a `GpxTrack`'s stored file, which paths would bypass signals, what
happens today when a row survives but its file is missing from storage (Risk
#3), and — critically — what the existing test suite *already* proves, so
Phase 2's plan targets real gaps rather than duplicating coverage that already
exists.

## Summary

The codebase's file-lifecycle machinery is small, deliberate, and already
**unusually well tested**. Two signal receivers in `gpx/signals.py`
(`post_delete` and `pre_save`) are the only places a `.gpx` file is ever
removed from storage by application code, and `tests/gpx/test_gpx_signals.py`
already exercises both receivers across model-delete, queryset-delete,
cascade-delete, rollback, and replace paths — always asserting
`default_storage.exists()` after a real commit via
`django_capture_on_commit_callbacks(execute=True)`, never merely "the receiver
fired." The admin file-replacement path (Risk #1's `pre_save` case) is also
already tested (`tests/gpx/test_gpx_admin.py`), and `reconcile_media` — the
deliberate out-of-band backstop for anything signals cannot see — has 26
tests covering nearly every documented guard condition.

**Risk #1 is therefore close to fully proven already.** The one real
structural gap found is a **two-level cascade**: `User` → `Trip` → `GpxTrack`
(deleting a user cascades through their trips into their tracks) is never
exercised — only the one-level `Trip` queryset cascade is. There is also one
untested boundary condition inside `reconcile_media`: the exact-equality edge
of the age cutoff (`modified > cutoff`, strict `>`, at line 218 of
`reconcile_media.py`) has no test proving a file aged to *exactly* the cutoff
is treated as orphaned rather than spared.

**Risk #3 is where the real, unclaimed gap is.** No code path in
`trips/views.py` or `gpx/views.py`'s detail rendering touches storage at all
— `build_map_config` and `build_trip_stats` read only stored columns
(`points`, `distance_meters`, etc.), so **a trip detail page renders
identically whether the file is present or has vanished from storage**: full
map, full stats, a `Track: {{ track.original_filename }}` line, and a
`Download` link that looks live. The only place the gap surfaces today is
`gpx:download`, which deliberately catches `OSError` (the `FileNotFoundError`
subclass `FileSystemStorage.open()` raises) and returns a logged `404` — and
that already has a test
(`test_a_row_whose_file_is_gone_returns_404_not_500` in
`tests/gpx/test_gpx_download.py`). What has **no** test anywhere is the
detail page itself: nothing asserts what a rider sees on the page — as
opposed to what happens if they click Download — when stats are already
computed and stored but the underlying file is gone. That combination (stats
rendered as if healthy + file absent + nothing on the page distinguishing the
two) is exactly the "nobody notices for months" shape Risk #3 names, and it
is the one genuinely new test Phase 2 needs to write for that risk.

## Detailed Findings

### File lifecycle machinery (Risk #1)

- `gpx/signals.py:29-77` — `discard_file_by_key(track_pk, storage_key, storage)`: the shared cleanup body both receivers close over. Deletes via `storage.delete(storage_key)` inside a broad `try/except Exception`, logging via `logger.exception` on failure, never raising. Takes scalars (pk, key, storage) rather than the model instance deliberately — the deletion `Collector` nulls `pk` after signals fire, and holding the instance would keep large `points` JSON blobs resident past commit.
- `gpx/signals.py:80-113` — `discard_file_of_deleted_track`, `@receiver(post_delete, sender=GpxTrack)`. Reads `instance.file.name` before scheduling; no-ops if empty. Schedules `transaction.on_commit(partial(discard_file_by_key, instance.pk, storage_key, instance.file.storage))`. Registering this receiver is what makes `Collector.can_fast_delete()` return `False` for `GpxTrack` (per `lessons.md` #10), forcing any cascade to materialize real instances instead of a fast bulk `DELETE`.
- `gpx/signals.py:116-182` — `discard_superseded_file_of_saved_track`, `@receiver(pre_save, sender=GpxTrack)`. Guards, in order: no-ops on fixture loading (`kwargs.get("raw")`), no-ops on insert (`instance.pk is None`), no-ops when `update_fields` is set and excludes `"file"` (this is what makes the stats-only backfill save a no-query no-op). Otherwise reads the *old* stored key with a deferred single-column query (`GpxTrack.objects.filter(pk=instance.pk).values_list("file", flat=True).first()`), no-ops if it's falsy or unchanged, and otherwise schedules the same `discard_file_by_key` on commit. Docstring explicitly names `bulk_create`, `bulk_update`, `QuerySet.update` as unreached by this receiver.
- `gpx/apps.py:8-19` — `GpxConfig.ready()` imports `gpx.signals` for its side effect so both `@receiver` decorators register exactly once.
- `gpx/models.py:8-17` — `gpx_upload_path(instance, filename)` ignores the user-supplied filename entirely and mints `gpx/{owner_id}/{trip_id}/{secrets.token_hex(16)}.gpx` — a fresh random key every time, which is why the admin change-form path can never silently overwrite the old file in storage (it always writes to a new key, stranding the old one unless `pre_save` reclaims it).
- `gpx/models.py:20-63` — `GpxTrack`: `trip = ForeignKey(Trip, on_delete=CASCADE)`, `file = FileField(upload_to=gpx_upload_path, max_length=255)`. No custom `save()`/`delete()` overrides — all cleanup lives in signals.
- `gpx/views.py:86-119` — `GpxUploadView.form_valid`: inside `transaction.atomic()`, reads `superseded = list(self.trip.tracks.select_for_update())` *before* saving the new track (line 113), lets `super().form_valid(form)` save the new row (an insert — `pre_save` no-ops), then `self.trip.tracks.filter(pk__in=[...]).delete()` (line 118) — a `QuerySet.delete()`, which (unlike `.update()`) fires `pre_delete`/`post_delete` per instance, so the superseded rows' files are reclaimed via the same `post_delete` receiver.
- `gpx/views.py:122-158` — `GpxDownloadView`: read-only; the storage-miss handling lives here (see Risk #3 below).
- `gpx/admin.py:13-29` — `GpxTrackAdmin`, `exclude = ("points",)`, no `readonly_fields` on `file` — the change form's file widget is editable, and saving it is an `UPDATE` (row survives) that the `pre_save` receiver exists specifically to catch.
- `trips/models.py:12-16` / `gpx/models.py:28` — `Trip.owner` is `CASCADE`, `GpxTrack.trip` is `CASCADE`. Confirms a two-level `User → Trip → GpxTrack` cascade is structurally possible.
- `trips/views.py:131-163` — `TripDeleteView` narrows `http_method_names` to keep raw HTTP `DELETE` unreachable, forcing deletion through `self.object.delete()` on a confirmed POST — signal-covered by design (comment at lines 144-147 states this explicitly).
- **Grep result**: no actual call site in `gpx/*.py` or `trips/*.py` uses `bulk_create`, `bulk_update`, or `QuerySet.update()` against `GpxTrack` today. Every hit for those terms is prose in docstrings/comments describing the *hypothetical* gap `reconcile_media` exists to cover, not a live code path. The only real `.delete(` calls touching `GpxTrack` rows/files are `gpx/views.py:118` (signal-covered), `gpx/signals.py:72` (the cleanup itself), and `reconcile_media.py:356,392` (deliberately out-of-band via `default_storage.delete()`).

**Synthesis — signal-covered vs. signal-blind:**

| Path | Covered? | Mechanism |
|---|---|---|
| Upload replacing an existing track | ✅ | `QuerySet.delete()` on superseded rows fires `post_delete` per row |
| Trip deletion (single or cascaded) | ✅ | Registered `post_delete` disables fast-delete, cascade materializes instances |
| Admin change-form file replacement | ✅ | `pre_save` compares old vs. new key on `UPDATE` |
| Admin default `delete_selected` bulk action | ✅ | Goes through the ORM `Collector`, same as any cascade |
| Stats-only backfill save | ✅ (correctly a no-op) | `update_fields` excludes `"file"`, guard short-circuits |
| `bulk_create`/`bulk_update`/`QuerySet.update()` on `GpxTrack.file` | ⚠️ not used today | None fire model signals; `reconcile_media` is the explicit backstop, not a receiver |
| Process death between storage write and commit | ⚠️ structural gap | `on_commit` callbacks never fire if the process dies first; `reconcile_media` backstop only |
| Files placed on the volume out-of-band (ops restore, manual copy) | ⚠️ structural gap | No row ever references them; `reconcile_media` is the only detector |

### Storage-miss behavior today (Risk #3)

- `trips/views.py:71-94` (`TripDetailView.get_context_data`) supplies `track`, `map_config`, and `stats` to `trips/templates/trips/trip_detail.html` — none of the three builders ever touches storage.
  - `gpx/map_config.py:38` (`build_map_config`) branches only on `track is None or not track.points` — `points` is a stored column.
  - `gpx/statistics.py:225,232-239` (`build_trip_stats`) reads only the four stats columns directly off the model instance — no `track.file` access anywhere in the function.
- `trips/templates/trips/trip_detail.html:66-69` unconditionally renders `Track: {{ track.original_filename }}` and a `Download {{ track.original_filename }}` link. **Nothing on this page can currently distinguish "file present" from "file missing."**
- `gpx/views.py:136-158` (`GpxDownloadView.get`) resolves the row via owner-scoped `get_object_or_404`, then:
  ```python
  try:
      stream = track.file.open("rb")
  except OSError:
      logger.exception(...)  # track_id, storage_key in extra
      raise Http404("The file for this track is not available.") from None
  ```
  `FileSystemStorage.open()` raises `FileNotFoundError` (an `OSError` subclass), so this is a deliberate 404, not a 500 — logged server-side, indistinguishable client-side from a nonexistent or foreign track pk.
- `gpx/exceptions.py` has no dedicated "file missing from storage" exception type — the case is modeled generically as `OSError`/`FileNotFoundError`, caught inline only in the download view.
- **User-facing outcome today**: (a) the trip detail page renders exactly as if the file were present — full map, full stats, a healthy-looking download link; (b) `gpx:download` 404s, logged, but reads the same as "not found" for any other reason. **No automated detection exists for this specific failure shape** (row present, file gone) — `reconcile_media` finds orphaned *files*, not the inverse.

### Existing test coverage — what's already proven

**`tests/gpx/test_gpx_signals.py`** (16 tests) — both receivers, always using `django_capture_on_commit_callbacks(execute=True)` and asserting `default_storage.exists()` (never "receiver called"):
- plain `Model.delete()`, `QuerySet.delete()` on `GpxTrack`, cascade from a `Trip` queryset delete, storage-delete failure absorption (`OSError` and `SuspiciousFileOperation`), empty-file no-op, rolled-back delete leaves file in place, replace via `track.file.save(...)`, ordinary save with no file change, `update_fields` short-circuit (with a no-query proof), rolled-back replacement, first save onto a never-stored row, raw fixture-load save, cleanup-failure-on-replacement logging.

**`tests/gpx/test_reconcile_media.py`** (26 tests) — report-only default, `--delete` reclaim vs. keep-referenced, age threshold (default spares fresh, `--min-age-minutes 0` lifts it, negative value refused via `CommandError`), `--allow-full-sweep` override plus the refusal itself plus single-referenced-file suppression, directory pruning (deepest-first, non-empty left alone, unreadable-directory skip), symlink escape guard, missing `MEDIA_ROOT`, failing deletes, vanishing-mid-walk, idempotent re-run.

**`tests/gpx/test_gpx_admin.py`** — admin change-form file replacement already tested: predecessor reclaimed, successor kept (with commit-callback execution and a directory-listing proof), and "saved without a new file keeps the stored one."

**`tests/gpx/test_gpx_download.py`** — `test_a_row_whose_file_is_gone_returns_404_not_500` already proves the download-path storage-miss behavior (row exists, file unlinked from disk, asserts 404 not 500). Also covers cross-user 404-not-403 and anonymous→login redirect.

**`tests/gpx/test_gpx_upload.py`** — the upload-replace path is already covered: `test_a_second_upload_replaces_the_first_and_removes_its_file` and a cleanup-failure-absorption test. Do not duplicate in Phase 2.

**`tests/gpx/test_gpx_track_model.py`** + **`tests/trips/test_trip_delete.py`** — trip cascade file cleanup covered at both the model level (`trip.delete()`) and the view-driven POST-delete path (with `django_capture_on_commit_callbacks(execute=True)`, N-row proof), plus a test that a raw HTTP `DELETE` verb is refused.

**`tests/gpx/test_gpx_statistics.py`** — `test_a_track_whose_file_is_missing_is_left_null_and_does_not_raise` covers the *backfill command's* storage-miss behavior (absorbed, logged, left null) — not the detail page.

**Fixtures**: `tests/gpx/conftest.py::trip`; `tests/conftest.py::make_gpx_track` (assigns a storage key but writes no bytes — itself a storage-miss fixture) and `::make_stored_track` (real bytes under a `tmp_path`-backed `MEDIA_ROOT`). No shared "storage-miss" fixture exists yet — every test builds it ad hoc.

### Real gaps for Phase 2 to fill (non-duplicate work)

1. **Two-level cascade: `User → Trip → GpxTrack`.** Only the one-level `Trip` queryset cascade (`test_a_trip_queryset_cascade_removes_the_track_files_it_never_loaded`) is tested. Deleting a `User` (e.g. admin's "delete selected users") should cascade two levels and still reclaim every track file — no test starts from `User.objects...delete()`. Worth a direct assertion given `Collector.can_fast_delete` behavior depends on which model in the chain has listeners.
2. **`reconcile_media`'s exact age-boundary edge.** The comparison is strict `>` (`reconcile_media.py:218`) — a file whose mtime equals the cutoff should be treated as an orphan (not spared), but no test proves the boundary itself (existing test only contrasts a full day vs. current mtime).
3. **The trip detail page's rendering when the row survives but the file is gone (Risk #3's core claim).** Nothing today asserts what the *rendered page* shows — as opposed to what `gpx:download` does — when stats are already computed/stored and the file has vanished. This is the one genuinely new test needed for Risk #3: tie "stats present" together with "file gone" and assert what marker (if any) the page gives the rider, since currently nothing does.
4. *(Minor, low priority)* No test drives file cleanup through the admin's default "delete selected tracks" bulk action specifically (as opposed to "delete selected trips" cascade, or the equivalent `QuerySet.delete()` test) — very likely already subsumed by existing queryset-level coverage.

## Code References

- `gpx/signals.py:29-182` — both cleanup receivers and their shared deletion helper
- `gpx/apps.py:8-19` — signal registration
- `gpx/models.py:8-63` — `gpx_upload_path`, `GpxTrack` model
- `gpx/views.py:86-119` — `GpxUploadView.form_valid` (replace path)
- `gpx/views.py:122-158` — `GpxDownloadView.get` (storage-miss 404)
- `gpx/admin.py:13-29` — `GpxTrackAdmin` (file-replacement admin path)
- `trips/models.py:12-16`, `gpx/models.py:28` — cascade chain
- `trips/views.py:131-163` — `TripDeleteView`
- `trips/views.py:71-94` — `TripDetailView.get_context_data` (no storage access)
- `gpx/map_config.py:38` — `build_map_config` (column-only)
- `gpx/statistics.py:225,232-239` — `build_trip_stats` (column-only)
- `trips/templates/trips/trip_detail.html:66-69` — unconditional track/download rendering
- `gpx/management/commands/reconcile_media.py:141-344` — flags and refusal/guard conditions
- `gpx/management/commands/backfill_gpx_stats.py` — backfill command, no refusal conditions, tally-based
- `gpx/migrations/0003_backfill_gpxtrack_stats.py:33-40` — guarded import of the backfill helper
- `gpx/constants.py:57` — `ORPHAN_MIN_AGE_MINUTES = 60`
- `tests/gpx/test_gpx_signals.py` — full receiver coverage
- `tests/gpx/test_reconcile_media.py` — full management-command coverage
- `tests/gpx/test_gpx_admin.py:59-131` — admin replacement path tests
- `tests/gpx/test_gpx_download.py:96-113` — download storage-miss test
- `tests/gpx/test_gpx_upload.py:311-386` — upload-replace tests
- `tests/trips/test_trip_delete.py:119-145` — view-driven cascade test
- `tests/gpx/test_gpx_statistics.py:84-107` — backfill storage-miss test
- `tests/conftest.py:121-183` — `make_gpx_track` / `make_stored_track` fixtures

## Architecture Insights

- The project deliberately decouples statistics rendering from file presence (per `AGENTS.md`): stats are stored columns, computed once at upload/backfill time, and never re-verified against storage on read. This is a considered tradeoff (cheap, reliable rendering) whose cost is exactly Risk #3 — nothing on the render path can notice file loss.
- Signal receivers take scalars (pk, storage key, storage backend) rather than the model instance when scheduling `on_commit` work, specifically to avoid holding large `points` JSON blobs resident past commit during a cascade.
- `reconcile_media` is explicitly the out-of-band backstop for everything model signals structurally cannot see — it is not a second receiver, it walks the filesystem directly.
- The admin's file-replacement path is the one case where a row survives a `file` change (as opposed to every deletion path where the row goes away too) — this is why it needed its own guard (`pre_save`) distinct from the `post_delete` receiver.

## Historical Context (from prior changes)

- `lessons.md` #10 — the `post_delete` receiver is what makes cascaded rows materialize at all (`Collector.can_fast_delete()`), confirmed directly against `django/db/models/deletion.py` in this research.
- `context/changes/edit-and-delete-trip/plan.md` (referenced by lessons.md #10) — prior design decision establishing the `transaction.on_commit` requirement for the `post_delete` receiver.
- `context/changes/testing-data-isolation-contract/` (Phase 1, complete) — established the pattern of asserting a status code *plus* a state/no-leak probe, and using `django_capture_on_commit_callbacks(execute=True)`, which Phase 2's existing tests already follow consistently.

## Related Research

- `context/foundation/test-plan.md` §2 (Risk Response Guidance for #1 and #3), §6.3/§6.5 (cookbook placeholders this phase will fill in)

## Open Questions

- Should Risk #3's new test assert a specific *deliberate* marker (e.g., a "track unavailable" banner) if the product doesn't currently render one at all, or should the test instead document the current behavior (page renders healthy, download 404s) as the accepted contract and assert that combination explicitly? This is a product decision for `/10x-plan`, not something research can resolve — the code today has no marker to assert.
- Whether the two-level `User → Trip → GpxTrack` cascade test belongs in Phase 2 (file-lifecycle) or would fit more naturally alongside `accounts/` test coverage — Phase 2's stated risks (#1, #3) are about file/row consistency regardless of which model triggers the cascade, so it fits here, but the fixture setup (creating and deleting a `User`) may pull in `accounts/` fixtures not otherwise used in `tests/gpx/`.
