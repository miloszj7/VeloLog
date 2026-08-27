<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Edit and Delete a Trip (S-04) + Future-Date Validation (E-08)

- **Plan**: `context/changes/edit-and-delete-trip/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-27
- **Verdict**: REVISE → **SOUND** after triage (all 4 findings fixed in the plan, 2026-08-27)
- **Findings**: 1 critical, 2 warnings, 1 observation — all FIXED

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | FAIL → PASS (F1, F4 fixed) |
| Plan Completeness | WARNING → PASS (F2, F3 fixed) |

## Grounding

13/13 paths ✓, 11/11 symbols ✓, brief↔plan ✓.

Verified against installed source rather than accepted from the plan:

- `Collector.can_fast_delete()` returns `False` when `post_delete` has listeners —
  `.venv/Lib/site-packages/django/db/models/deletion.py:186-206` ✓ (the plan's
  load-bearing mechanism claim holds).
- `DeleteView[_M, _FormT]` takes **two** parameters and `SuccessMessageMixin[_F]` is
  bound to `BaseForm` — `django-stubs/views/generic/edit.pyi:82`,
  `django-stubs/contrib/messages/views.pyi:8-12` ✓.
- `BaseDeleteView.post` sets `self.object = self.get_object()` before `get_form()` —
  `django/views/generic/edit.py:248-258` ✓, so the owner-scoped queryset 404s a foreign
  POST with no override, as the plan claims.
- `INSTALLED_APPS` lists bare `"gpx"` (`velo_log/settings.py:61`), so `GpxConfig.ready()`
  is reached through app-config autodiscovery with no settings change ✓.
- `[tool.coverage.run] source = ["accounts", "trips", "gpx", "velo_log"]`
  (`pyproject.toml:61`) already covers a new `gpx/signals.py` ✓ — `lessons.md` #4 does
  not apply, as the plan states.
- Every date literal in `tests/` is `2026-01-01`, `2026-06-01` or `2026-07-01`, all past
  today — Phase 4 breaks no existing test ✓.
- Progress↔Phase mechanical contract: exactly one `## Progress` (`:820`), five
  `### Phase N` subsections matching the five `## Phase N` bodies, 27 Success Criteria
  bullets ↔ 27 numbered checkboxes, zero `- [ ]` outside the Progress section ✓.

`docs/reference/contract-surfaces.md` does not exist — the contract-surfaces check was
skipped, per the skill's opt-in rule.

## Findings

### F1 — "Wrong verb → 405" is false; HTTP DELETE destroys the trip

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Implementation Approach (fixed matrix) · Phase 3 §5 (Tests) · Testing Strategy → Integration Tests
- **Detail**: The plan asserts "wrong verb → **405**" for every new owner-scoped surface,
  and Phase 3 makes it explicit: "`PUT`/`DELETE` verb → 405". Neither holds.

  `BaseDeleteView(DeletionMixin, FormMixin, BaseDetailView)` still inherits
  `DeletionMixin.delete()` in the installed Django 6
  (`.venv/Lib/site-packages/django/views/generic/edit.py:215-232`, `:240`).
  `View.dispatch` resolves a handler with `getattr(self, request.method.lower(), ...)`
  (`django/views/generic/base.py:139-142`) and `_allowed_methods` lists any method the
  class has an attribute for (`base.py:181-182`). So an HTTP `DELETE` at
  `/trips/<pk>/delete/` runs `DeletionMixin.delete()` — `get_object()`,
  `get_success_url()`, `self.object.delete()`, 302 — bypassing the confirmation page and
  the empty `Form` entirely, and (via Phase 2's receiver) taking the GPX file with it.
  Django's test client does not enforce CSRF by default, so `client.delete(url)` returns
  302 with the trip gone, not 405. Phase 3's test will fail, and it will be failing on a
  real defect rather than a bad assertion.

  `TripUpdateView` has the milder half of the same problem: `ProcessFormView.put` calls
  `self.post(*args, **kwargs)` (`edit.py:155-157`), and `ModelFormMixin.get_form_kwargs`
  binds `self.request.POST` for `"PUT"` too — which is empty for a PUT request — so PUT
  returns a 200 re-render with field errors, never a 405.

- **Fix A ⭐ Recommended**: Set `http_method_names = ["get", "post"]` on `TripUpdateView`
  and `TripDeleteView`, with a comment naming what it closes; keep the 405 assertions as
  the plan wrote them.
  - Strength: Already the repo's idiom — `GpxUploadView.http_method_names = ["post"]`
    (`gpx/views.py:62-64`), asserted at `tests/gpx/test_gpx_upload.py:420`, the suite's
    only existing 405. Keeps the plan's fixed matrix true as written and closes the
    confirmation-free delete route.
  - Tradeoff: One extra line per view plus a comment explaining why the default is wrong.
  - Confidence: HIGH — mechanism read directly from the installed Django source, not recalled.
  - Blind spot: None significant.
- **Fix B**: Leave the framework defaults in place and rewrite the assertions to match
  actual behaviour (DELETE → 302, PUT → 200).
  - Strength: No production code change; documents what the framework really does.
  - Tradeoff: Leaves a live, confirmation-free, file-destroying delete route, which
    contradicts Phase 3's own rationale that "the confirmation page is the guard".
  - Confidence: HIGH — behaviour is identical either way; only the response changes.
  - Blind spot: Whether any future surface (an API, an HTMX control) would want that route.
- **Decision**: FIXED via Fix A ⭐ — `http_method_names = ["get", "post"]` added to both view contracts (Phase 1 §1, Phase 3 §1); a *Verb narrowing* block added to Critical Implementation Details; the fixed-matrix paragraph now states the 405 leg is earned, not free; Phase 1 §5 gains an owner-`PUT` → 405 case; Phase 3 §5's `DELETE` case is paired with a still-exists assertion.

### F2 — Phase 4 names a ModelForm `Meta` key that does nothing

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 §1 — "Add `labels` and/or `help_text` to `Meta`"
- **Detail**: `ModelFormOptions` reads `getattr(options, "help_texts", None)` — **plural**
  (`.venv/Lib/site-packages/django/forms/models.py:268`, applied at `:231-232`). A
  `help_text = {...}` attribute on `TripForm.Meta` is silently ignored: no error, no hint
  rendered, and every automated gate stays green. Only manual criterion 4.9 ("date field
  carries a label or hint") would catch it — a silent no-op behind a passing gate is
  precisely the class `lessons.md` exists to head off. "and/or" also hands the
  implementer a choice between two mechanisms with no criterion for picking one.
- **Fix**: Name `help_texts` (plural) explicitly, and pick one mechanism — `labels` for
  the field caption, or `help_texts` for a hint beneath it — rather than "and/or".
- **Decision**: FIXED — Phase 4 §1 names `help_texts` (plural) with the `forms/models.py:268` citation and commits to that one mechanism over `labels`; the Migration note's singular spelling corrected; Phase 4 §2 gains a rendered-help-text assertion; criterion and checkbox 4.9 reworded to require it rendered on the page.

### F3 — Phase 5 misses the third place the roadmap records S-04's status

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 5 §1 (Roadmap status) · Success Criterion 5.1
- **Detail**: The contract says to update "both places the `/10x-roadmap` template keeps
  it" — the `## At a glance` row (`roadmap.md:33`) and the item body's `- **Status:**`
  line (`:101`). There is a third: the **Backlog Handoff** table at `roadmap.md:121`,
  where S-04 still reads `Ready for /10x-plan: no` and `Notes: Waiting on S-02` — stale
  since S-02 shipped. The S-02 precedent two rows up (`:118`) shows the intended end
  state: `yes` plus "Planned and implemented (Phase 5, `/10x-implement …`)".

  Criterion 5.1 is scoped to the two sites the plan already knows about
  (`grep -n "S-04" … shows done in both the glance table and the item body`), so it
  cannot catch the miss. This is the exact shape of `lessons.md` #5. Note that S-03's row
  (`:120`) is already stale the same way — a pre-existing gap, but one this slice's
  criterion would silently reproduce rather than close.
- **Fix**: Add the Backlog Handoff row to the Phase 5 contract, and widen 5.1 to assert
  that no "Waiting on S-02" text remains on the S-04 row. Decide explicitly whether S-03's
  row is fixed in the same pass or deliberately left.
- **Decision**: FIXED — Phase 5 §1 now names all three sites, including the Backlog Handoff row (`:121`), with the S-02 precedent; criterion and checkbox 5.1 widened to a `grep` for "Waiting on S-02" returning nothing. Scope decision: S-03's stale row (`:120`) is fixed in the same pass; S-05's "Waiting on S-03" note is deliberately left to the next roadmap pass.

### F4 — Confirmation page claims a GPX file goes, even when there is none

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 3 §3 (The confirmation page) · Manual Testing step 4
- **Detail**: The contract specifies "a sentence stating the attached GPX file goes too,
  since that is the part a rider cannot re-derive", with no branch on whether a track
  exists — while Manual Testing step 4 deletes a trip with no GPX file at all. That rider
  is warned about losing a file that is not there. The repo already branches on exactly
  this condition twice in the sibling template: `trips/templates/trips/trip_detail.html:22`
  and `:61`.
- **Fix**: Wrap the sentence in `{% if trip.tracks.all %}`. Keep it in-template rather
  than adding a context key — `trip_confirm_delete.html` is rendered only by
  `TripDeleteView`, so the cross-app context-coupling trap the plan calls out does not
  apply here either way.
- **Decision**: FIXED — Phase 3 §3 wraps the GPX sentence in `{% if trip.tracks.all %}` with the in-template rationale; Phase 3 §5 gains a trackless-trip confirmation GET asserting the sentence is absent; criterion and checkbox 3.11 and Manual Testing step 4 widened to cover it.
