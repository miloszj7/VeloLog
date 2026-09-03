<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Multi-stage GPX upload

- **Plan**: `context/changes/multi-stage-gpx-upload/plan.md`
- **Scope**: Full plan — all 7 phases (every `## Progress` row checked, epilogue commit `06a1643` landed)
- **Date**: 2026-09-03
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 3 observations

## How this review relates to the previous one

`reviews/impl-review-phases-1-5.md` reviewed Phases 1-5 on the same date and closed all ten of
its findings. **Every one of those fixes was verified present on disk in this pass** — including
the two structural ones: `gpx/statistics.py:59-66` carries the six-entry `STATS_FIELDS` with
`_writable_stats_fields` deriving `update_fields` from the row's own model (`:84-102`), and
`gpx/migrations/0003_backfill_gpxtrack_stats.py:23-28` pins `STATS_COLUMNS_AT_0002` instead of
importing the live tuple. Criterion 3.15, the one item that review left open by decision, is now
genuinely closed: the measured figures live at `gpx/constants.py:19-34`, with the "not yet
calibrated" wording gone and the conditions that would invalidate them recorded beside the
constant.

This review therefore weights **Phases 6 and 7, which had never been reviewed**, plus cross-phase
interaction and the post-review fix commits (`879bc9f`, `9196240`, `f351b24`).

**No finding below is a behavioral defect.** All four warnings are stale-claim or guard-quality
items — the shape this repo has escalated to lessons #5 and #11 and treats as real. The shipped
behavior is sound: the drift sweep found no DRIFT, no MISSING and no unauthorised EXTRA across
all seven phases, and the safety sweep found nothing in security or data safety.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | WARNING |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## What was verified green

Re-run in this review, on the branch tip:

- `SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= pytest --cov` — **379 passed, 2 skipped**, coverage **96.39%** (`fail_under = 80`)
- `pytest -m bite_proof` — **6 passed** (with `FORCE_COLOR` cleared; see Notes)
- `pytest tests/test_assertion_strength.py` — 3 passed, no new waivers
- `pytest tests/test_static_references.py` — 14 passed under the production manifest backend
- `ruff` / `black` / `mypy --strict` — clean; `isort` exits 0 (see Notes)
- `manage.py check` — no issues; `makemigrations --check --dry-run` — no changes detected
- `collectstatic --noinput` — 400 post-processed
- Migrations on a scratch SQLite file: forward from zero through `0005`, backward to `0003`
  (unapplying `0005` then `0004`), forward again — all clean
- **N+1 probe (mine, run and discarded):** the trip detail page costs **4 queries at 1, 3 and 5
  stages**. The plan's "there is no DB N+1 here" claim (`## Performance Considerations`) is true.

Scope guardrails from `## What We're NOT Doing`, all verified clean: no stage-removal route
(`gpx/urls.py` still has two, `OBJECT_SCOPED_ROUTES` unchanged), no `Trip` migration
(`trips/migrations/` is still `0001_initial.py` alone), no `order`/`position` column, no
`Sum`/`aggregate`/`annotate` anywhere in `gpx/` or `trips/`, and no re-parse at render —
`parse_gpx_bytes` is called only from `gpx/forms.py:60` (upload) and `gpx/statistics.py:124`
(backfill).

Manual criteria are all `[x]` and were confirmed by the user at each phase's `/10x-implement`
gate. The one manual item whose deliverable was a recorded artifact rather than an observation —
3.15's page-weight measurement — has that artifact on disk and honestly caveated (TTI was not
instrumented; the payload figure is named as the proxy).

## Findings

### F1 — `gpx/signals.py` still documents replace-on-upload, the semantics this change removed

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `gpx/signals.py:6`, `gpx/signals.py:160-163`
- **Detail**: The module is correct under ADD semantics and needed no code edit — which is
  exactly why its prose was never revisited. Two claims are now false. The module docstring
  lists the paths routed through it as "a trip cascade, the admin's `delete_selected`, **an
  upload replacing its predecessor**, a bare `QuerySet.delete()` and a file replaced on a row
  that stays" (`:6`) — the third is gone. And the `pre_save` early return explains itself as:
  "Returning here is what keeps this receiver off `GpxUploadView.form_valid`, **whose superseded
  rows are *deleted*** and so already covered by `discard_file_of_deleted_track`" (`:160-163`).
  `GpxUploadView.form_valid` (`gpx/views.py:95-115`) supersedes nothing and deletes nothing. The
  early return still matters — every upload is an INSERT — but the stated reason for it is a
  behavior that no longer exists, so the next reader is told the receiver is skipped because
  something else cleans up, when in fact there is nothing to clean up.

  This is the same shape the change fixed four times elsewhere (`GpxTrack`'s docstring,
  `gpx/stages.py`'s, `AGENTS.md`'s `gpx/` bullet, `gpx/map.js`'s catch) and lessons #5 and #11
  in their exact wording. `AGENTS.md:23` already describes the new split correctly, so the
  authoritative doc and the module it describes now disagree.
- **Fix**: Reword both to name the two paths that actually remain — the admin change form and a
  direct `FieldFile.save()` on a surviving row — and drop the `form_valid` clause from the
  `pre_save` comment, keeping the "every upload is an INSERT, and this costs the hot path zero
  queries" half, which is still true and still the reason.
- **Decision**: FIXED — module docstring drops the removed replace-on-upload path and names the two that still supersede (admin change form, direct `FieldFile.save()`); the `pre_save` early return now explains itself as "every upload is an INSERT, so there is nothing to reclaim" instead of citing `form_valid`'s deleted rows.

### F2 — `map.js`'s catch comment promises an all-or-nothing fallback the code does not deliver

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `gpx/static/gpx/map.js:148-152`
- **Detail**: The comment added by the previous review's F9 fix reads: "a throw in any of the
  three loops above — a malformed `segment.points`, or an `icons[marker.kind]` miss handing
  Leaflet `undefined` — lands here **before the fallback is removed, so every stage falls back
  together, not just the bad one**."

  The first half is literally true (fallback removal is at `:117`, after all three loops), but the
  conclusion does not follow, and this file's own header comment says why: "initialising a map
  appends panes to `#map` rather than emptying it" (`:35-37`). By the time the marker loop can
  throw, `L.map()`, the tile layer and every already-processed polyline are on screen. The user
  sees a **live, partially drawn tour with "The map could not be loaded." still sitting inside
  the container** — not a clean fall-back, and precisely the "fully rendered live map sitting
  behind the 'could not be loaded' message, contradicting this file's own contract" that the
  comment at `:112-116` says the removal ordering exists to prevent.

  The underlying behavior is pre-existing (v1 had the same init → draw → remove-fallback order),
  so this is not a regression. What is new is the comment asserting a multi-stage all-or-nothing
  guarantee that was never implemented, in the file whose entire stated contract is that the
  fallback message is the user-visible truth about a failed draw.
- **Fix A ⭐ Recommended**: Reword the comment to state what actually happens — a throw leaves
  whatever was already drawn on screen alongside the fallback paragraph — and keep the existing
  pointer that a stage the client cannot draw is `gpx/map_config.py`'s job to exclude.
  - Strength: The behavior is pre-existing, accepted for a year, and correct enough in practice
    (`map_config.py` genuinely does skip a point-less stage and emits only kinds it also builds
    icons for, so no known payload reaches the throw). Fixing the claim rather than the code is
    the minimum edit that makes the file honest, and it is what lessons #5/#11 actually ask for.
  - Tradeoff: Leaves a real, if unreachable, half-drawn-map failure mode undefended.
  - Confidence: HIGH — the failure path is verified by reading, and no payload the server can
    currently emit reaches it.
  - Blind spot: Not exercised under test; there is no JS test harness in this project, so neither
    option can be proven by the suite.
- **Fix B**: Make the catch genuinely all-or-nothing — call `map.remove()` and restore the
  container to its fallback-only state in the handler before returning.
  - Strength: Delivers the guarantee the comment claims and the header contract implies.
  - Tradeoff: Adds untested teardown code to the one path that already failed once, on a file
    with no test harness; a bug in the handler turns a partial draw into a blank container.
  - Confidence: MEDIUM — `map.remove()` is documented 1.x API, but the interaction with an
    already-removed fallback node is not something the suite can check.
  - Blind spot: Whether `map.remove()` reliably restores `#map` to a state the fallback renders
    correctly in has not been verified in a browser.
- **Decision**: FIXED via Fix A — the catch comment now states what actually happens (panes are appended, so a throw leaves the already-drawn stages on screen beside the fallback sentence) and names the reason it is tolerated: `gpx/map_config.py` keeps the throws unreachable, not the catch. Behavior unchanged; Fix B's teardown was declined as untested code on an untestable path.

### F3 — `backfill_gpx_stats --help` never mentions instants, on the one path an operator reads under pressure

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `gpx/management/commands/backfill_gpx_stats.py:29`, `:36-38`
- **Detail**: Phase 6 §3 required that the command be documented as refilling instants, and both
  the module docstring (`:9-11`, "with `--all` for the instants, since the default filter below
  cannot reach a row whose statistics already landed") and `AGENTS.md:37` say so clearly. The two
  argparse strings — the only ones `manage.py backfill_gpx_stats --help` prints — do not:

  ```python
  help = "Recompute the statistics columns on stored GPX tracks from their files."
  ...
  "Reprocess every track, not only those whose statistics are null — for a "
  "track whose file was replaced or whose stored figures are stale."
  ```

  This is the documented recovery when migration `0005` runs against a misconfigured `MEDIA_ROOT`
  and fills nothing — a migration that cannot be re-applied. The operator in that situation is
  reading `--help`, not the module docstring or `AGENTS.md`; they see "statistics", have no reason
  to reach for `--all`, and the instants stay null with the command reporting success. That is
  E-05's "documented steps that reported success and recovered nothing" shape, which Phase 6 §3
  explicitly reasons about avoiding — reached from the other end.
- **Fix**: Add the instants to both strings — `Command.help` becomes "Recompute the statistics
  columns and stage instants…", and `--all`'s help gains the clause the module docstring already
  carries ("…and the only way to refill stage instants on a row whose statistics are already
  present").
- **Decision**: FIXED — `Command.help` reads "Recompute the statistics columns and stage instants…" and `--all`'s help gained "…and the only way to refill stage instants on a row whose statistics are already present." Verified against real `--help` output.

### F4 — the query-count pin is asserted only against a single-stage trip, so the change's central performance claim is unguarded

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `tests/trips/test_trip_detail_stats.py:39`, `:280`
- **Detail**: `DETAIL_PAGE_QUERIES = 4` is asserted once, against a one-stage trip. The plan's
  `## Performance Considerations` rests a load-bearing claim on it — "There is no DB N+1 here to
  confuse it with — `build_stages` materialises `ordered_stage_tracks` once with `list(...)`" —
  and then concedes in the same paragraph that the pin covers "only against a single-stage trip".

  **The claim is true**: I probed the page at 1, 3 and 5 stages and it costs 4 queries every time.
  But nothing in the suite would notice if it stopped being true. The regression this change makes
  possible — a per-stage deferral or a `.only()` narrowing that costs one query per stage — is
  invisible to a one-stage assertion by construction, and the docstring at `:34-38` ("a jump of
  four means the track's columns went deferred and are being refreshed one at a time") describes a
  guard the single-stage case cannot deliver for the multi-stage page.

  Carried forward from the Phases 1-5 review, which recorded it as a nit. It is promoted here
  because the change is now complete, the page is definitively multi-stage, and the plan cites
  this pin as the evidence for its performance section.
- **Fix**: Parametrize the query-count test over one and three stages, asserting the same
  `DETAIL_PAGE_QUERIES` for both — one line, and it turns a true claim into a guarded one.
- **Decision**: FIXED — the query-count test is parametrized over one and three stages, both asserting `DETAIL_PAGE_QUERIES`; `DETAIL_PAGE_QUERIES`'s own comment now describes a count that must not scale with stage count. Both cases pass at 4 queries.

### F5 — start and finish markers are emitted unconditionally while break markers are gated on chronology

- **Severity**: 👁 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Architecture
- **Location**: `gpx/map_config.py:71-78`
- **Detail**: `markers` seeds `start` at `drawable[0]`'s first point and `finish` at
  `drawable[-1]`'s last point unconditionally (`:72-73`); `break` markers are appended only
  `if established` (`:78`), with a comment explaining that "an upload-ordered boundary asserts
  nothing about where the rider actually stopped and resumed."

  When chronology is not established the sequence *is* upload order — so a pin titled "Finish"
  lands on the last-**uploaded** stage's last point, on a page that simultaneously prints "the
  stages are shown in upload order because the files carry no ride timestamps"
  (`trip_detail.html:123`). The reasoning that suppresses breaks applies to the finish pin with
  equal force; the plan authorises the asymmetry (Phase 3 §3 specifies exactly this), so it is not
  drift, but no line of code or plan prose says why an upload-ordered "Finish" is an acceptable
  claim while an upload-ordered break is not.

  It may well be deliberate and right — a trip always has a first and a last point regardless of
  ordering evidence, whereas a *break* is a positive assertion about rider behavior. That
  distinction just is not written down anywhere, and it is the kind of reasoning the rest of this
  change records carefully.
- **Fix A ⭐ Recommended**: Record the reasoning in `gpx/map_config.py` beside the marker list —
  one comment distinguishing "the route has endpoints under any ordering" from "a break asserts
  the rider stopped here".
  - Strength: Matches how every other judgement call in this change is handled, and costs nothing.
    The distinction is defensible on its face.
  - Tradeoff: Leaves the title "Finish" reading as a ride-order claim on an upload-ordered page.
  - Confidence: HIGH — the reasoning is sound and the plan already chose this shape deliberately.
  - Blind spot: Whether a rider actually reads "Finish" as "end of the tour" rather than "end of
    the drawn line" has not been tested with anyone.
- **Fix B**: Gate the two pins the same way — neutral titles ("Route start" / "Route end") when
  chronology is not established.
  - Strength: Makes one predicate govern every claim the map makes, which is the "one predicate,
    three consumers" discipline the plan states as a Critical Implementation Detail.
  - Tradeoff: Touches a payload contract five tests pin, for a wording nuance; and the plan
    deliberately specified unconditional pins.
  - Confidence: MEDIUM — clearly implementable, but it reopens a settled plan decision.
  - Blind spot: Whether any test asserts the literal titles "Start"/"Finish" on an untimed trip.
- **Decision**: FIXED via Fix A — a comment beside the marker list now records the distinction: a drawn route has a first and last point under any ordering, so those two pins describe the line on screen, whereas a break is a positive assertion about rider behavior that upload order cannot support. Payload contract unchanged.

### F6 — `MARKER_ICON` / `MARKER_ICON_RETINA` have no production consumer, and their comment still says they do

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `gpx/constants.py:72-79`
- **Detail**: After Phase 5, `gpx/map_config.py` imports `MARKER_SHADOW` and the three new stage
  SVGs, and nothing else. A repo-wide grep finds `MARKER_ICON` and `MARKER_ICON_RETINA` only in
  `gpx/constants.py` itself and in `tests/test_static_references.py:36-37,53-55`, which asserts
  they survive `collectstatic` — a test proving two unreferenced vendored PNGs are collectable.
  Their comment (`:72-77`) still reads "Paths of the Leaflet marker images `gpx/map_config.py`
  hands to the template", now true of only `MARKER_SHADOW`.

  The Phases 1-5 review recorded this and suggested "a one-line comment saying they are the
  deliberate fallback pin would settle it"; that comment was not added, so the stale one still
  stands.
- **Fix**: Split the comment — keep `MARKER_SHADOW` under the existing sentence, and either drop
  the two unused constants with their `STATIC_REFERENCES` entries, or give them their own line
  saying they are the retained upstream pin, kept collectable deliberately.
- **Decision**: FIXED via the drop branch — `MARKER_ICON` / `MARKER_ICON_RETINA` and their `STATIC_REFERENCES` entries are gone; the surviving comment covers `MARKER_SHADOW` alone and records that the two vendored PNGs stay on disk deliberately, because `SHA256SUMS` pins the upstream Leaflet drop and removing them would fail that check for no gain.

### F7 — a migration-pin test's docstring points at the assertion one line above the one that delivers its claim

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/gpx/test_gpx_statistics.py:292`, `:299-302`
- **Detail**: `test_the_instants_migrations_pinned_columns_match_the_state_it_runs_at` ends its
  docstring with "**Equality rather than a subset**, because a name `0004`'s model does not carry
  is exactly that failure" — and the assertion immediately below it is
  `assert set(STATS_COLUMNS_AT_0004) <= historical_fields`, a subset check.

  The test is correct: the equality *is* delivered, three lines later, by
  `assert _writable_stats_fields(historical_track()) == list(STATS_COLUMNS_AT_0004)`. Only the
  docstring's pointer is off, and it lands on the line that most looks like a contradiction of it.
  Lesson #11 one notch down — the claim is honoured by the test as a whole, not by the line a
  reader will check it against.
- **Fix**: Reword to name which assertion carries the equality — "the subset check below is the
  cheap half; the equality that catches the real failure is `_writable_stats_fields(...) == …`".
- **Decision**: FIXED — the docstring now names both assertions and says which carries the claim: the subset check is the cheap half, and the equality that catches the real failure is `_writable_stats_fields(historical_track()) == list(STATS_COLUMNS_AT_0004)`.

## Triage outcome

All seven findings triaged and **all seven fixed** — six as recommended, one (F6) on the
`drop` branch rather than the `keep and re-comment` branch. No finding was skipped,
dismissed or accepted as risk, and no lesson was recorded: every item was an instance of
lessons #5 and #11, which are already on the register.

Every fix is a comment, docstring, help-string or test change. **No production behavior
was altered by this triage** — F2 was closed by correcting the claim rather than adding
the teardown (Fix B), and F5 by recording the reasoning rather than regating the pins
(Fix B). The one non-comment change to shipped code is F6's deletion of two unreferenced
constants.

Re-run on the branch tip after all seven fixes:

- `SECRET_KEY=… DEBUG=False ALLOWED_HOSTS= pytest --cov` — **378 passed, 2 skipped**,
  coverage **96.38%**. The count moves from the review's 379 exactly as the fixes predict:
  −2 parametrized cases from F6's dropped `STATIC_REFERENCES` entries, +1 from F4's new
  three-stage case.
- `pytest -m bite_proof` — **6 passed** (with `FORCE_COLOR` cleared, per the note below)
- `ruff` / `black` / `mypy --strict` — clean; `isort` exits 0 with the same two pre-existing
  skips
- `manage.py check` — no issues; `makemigrations --check --dry-run` — no changes detected
- `collectstatic --noinput` — 400 post-processed, so the static-reference tests ran against
  a real manifest rather than skipping
- `manage.py backfill_gpx_stats --help` — inspected directly; both strings now name the
  stage instants, which was F3's whole point

The items under *Notes and nits* were not in scope for this triage and remain open — in
particular the `FORCE_COLOR` fragility of the bite-proof harness, which the review argues
deserves its own change.

## Notes and nits (not findings)

- **`pytest -m bite_proof` reports all six shapes broken when `FORCE_COLOR` is set.** Reproduced
  here (this shell exports `FORCE_COLOR=3`): all six fail with the guard's real failure message
  present but wrapped in ANSI escapes, so the plain-string `fragment` match misses. With
  `FORCE_COLOR=` / `NO_COLOR=1` all six pass. Pre-existing, recorded by the Phases 1-5 review as
  out of scope, and CI sets no `FORCE_COLOR` — but the credibility harness lies in the unsafe
  direction (reporting protection broken when it is not, which trains a reader to ignore it), and
  it deserves its own change.
- **`isort` skips two test files while exiting 0.** `tests/gpx/test_gpx_parsing.py` and
  `tests/gpx/test_gpx_statistics.py` fail to parse on a charmap `UserWarning` over a `→`
  character; the run prints "Skipped 3 files" and exits 0. **Verified pre-existing on `master`**
  (`d34b0a4` already contains the `→` in both files), so out of this change's scope — but the
  import-order gate does not cover those files and reports success.
- **`trip_confirm_delete.html:19,25,26`** — `trip.tracks.exists` then `trip.tracks.count` twice is
  `EXISTS` + `COUNT` + `COUNT`; templates do not memoize related-manager calls. Three queries
  where one `{% with %}` would do. Trivial on a page rendered once per delete; recorded again
  because this change is what took it from one query to three.
- **`gpx/stages.py`** — of the module's four public callables only `trip_span` carries the Google
  `Args:`/`Returns:` sections its siblings use (`gpx/availability.py`, `gpx/map_config.py`,
  `gpx/statistics.py`). The other three are prose-only. The prose is thorough, so this is a style
  mismatch rather than a documentation gap.
- **`context/foundation/roadmap.md:42,75`** — S-01 is `in-progress` while `change.md` reads
  `implemented`. This is the designed state: `/10x-archive` performs the `done` flip. Worth
  running before or at merge so the roadmap is true in `master`.
- **`0005`'s `RunPython` body never executes under `pytest`** — migrations run against an empty
  in-memory database, the same limitation `gpx/statistics.py:25-27` already documents for `0003`.
  Compensated as the plan intends: the helper is unit-tested directly, the column pin is asserted
  against the real migration graph's state at `0004`, and a forward/backward run over a seeded
  pre-`0004` row was done out of band. No action.
- **`ended_at` is now read** — the Phases 1-5 review noted it was written but read by nothing;
  Phase 7's `trip_span` closes that. The forward-compat note in that review is superseded.
