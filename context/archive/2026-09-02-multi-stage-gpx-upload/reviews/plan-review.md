<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Multi-stage GPX upload

- **Plan**: `context/changes/multi-stage-gpx-upload/plan.md`
- **Mode**: Deep
- **Date**: 2026-09-02
- **Verdict**: REVISE → **SOUND** after triage (all 7 findings fixed in `plan.md`, 2026-09-02)
- **Findings**: 3 critical, 3 warnings, 1 observation

The approach is sound and unusually well grounded — every risky claim that was checked
came back accurate, including the inverted-risk finding, the discarded parse instants, and
both the ORM and gpxpy behaviours the plan says it probed. All three criticals are
localized phase-contract edits, not a change of approach.

## Verdicts

| Dimension | At review | After triage |
|-----------|-----------|--------------|
| End-State Alignment | FAIL | PASS |
| Lean Execution | PASS | PASS |
| Architectural Fitness | PASS | PASS |
| Blind Spots | FAIL | PASS |
| Plan Completeness | WARNING | PASS |

Every finding was fixed in the plan rather than accepted or deferred, so no residual risk
is carried into implementation. Two fixes changed the plan's *shape* and are worth knowing
before reading it: the phase order (markers now Phase 5, backfill Phase 6) and the
deliberate one-phase context shim in Phase 3 §4.

## Grounding

16/16 paths ✓, 9/9 symbols ✓, brief↔plan ✓, Progress↔Phase contract ✓ (7 phases,
63 steps, every Success Criteria bullet matched; no checkboxes outside `## Progress`;
`/10x-implement` keys on `### Phase N:` so the `*(cuttable)*` suffix present in body
headings but absent from Progress parses fine).

Probes run in this repo's venv:

- Django 6.0.8 / SQLite 3.50.4 — `F(...).asc(nulls_last=True)` compiles to native
  `ORDER BY ... ASC NULLS LAST` (`supports_order_by_nulls_modifier` is `True`), and the
  three-term `order_by` survives Django's column de-duplication when the terms name
  distinct columns. ✓
- gpxpy 1.6.2 — Z-suffixed timestamps yield `SimpleTZ('Z')`-aware datetimes, offset-less
  ones yield **naive** datetimes, an untimed file yields `TimeBounds(None, None)`, and
  `.astimezone(UTC)` normalises correctly from both `SimpleTZ('Z')` and `SimpleTZ('02:00')`.
  ✓ Exactly as `plan.md:61-66` states.

Verified clean, so it need not be re-litigated:

- `_assert_no_track_was_attached` (`tests/test_ownership_matrix.py:158-174`) does compare
  the full pk list and does hold under ADD, as `plan.md:854-856` claims.
- `gpx/forms.py:84-93` assigns exactly ten instance fields ending with
  `elevation_loss_meters`, as Phase 1 §4 claims. `Meta.fields = ("file",)` means the two
  new columns need no form field, matching the existing contract.

## Findings

### F1 — A PRD must-have lives entirely inside a cuttable phase

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: End-State Alignment
- **Location**: Phase 6 *(cuttable)*; Implementation Approach (`plan.md:137-140`)
- **Detail**: `prd.md:96-97` states the acceptance criterion as "the three kinds are
  distinguishable at a glance, **without hovering**, on desktop and at phone width", and
  `prd.md:127` lists distinct start/end/stage-break markers as **must-have** in Scope of
  Change. The Primary Success Criterion (`prd.md:46`) repeats it. Phase 3 emits all three
  marker kinds sharing "the same existing Leaflet pin blob" (`plan.md:476`) —
  distinguishable only by hover title. Phase 6, which delivers actual distinctness, is
  marked *(cuttable)* and ordered *after* Phase 5 in the cut list. The plan knows this:
  Phase 6's Overview says the pins are "what the Primary Success Criterion's 'distinct
  markers' clause asks for and a tooltip cannot deliver on a phone" (`plan.md:700-701`) —
  then leaves it cuttable anyway. Phases 1-5 can therefore all go green with the
  milestone's must-have unmet.
- **Fix A ⭐ Recommended**: Promote Phase 6 out of the cut list and run it before Phase 5.
  - Strength: It is the smallest of the three cuttable phases — three SVGs, three
    constants, three `STATIC_REFERENCES` entries, and no `map.js` change, because Phase 3
    already engineered the keyed `icons` map to make it "a two-URL swap rather than a
    rewrite" (`plan.md:476`). Phase 5 (backfill) is genuinely cuttable — `plan.md:915`
    shows untimed rows are legal and re-fillable later — so it is the correct thing to sit
    last.
  - Tradeoff: Cutting Phase 5 instead degrades US-02's own demo path
    (`plan-brief.md:101-102`), so the week's slack buys less.
  - Confidence: HIGH — the cost asymmetry is visible in the two phases' own contracts, and
    Phase 6 has no dependency on Phase 5.
  - Blind spot: Hand-authoring three legible 25×41 pins is unestimated; if it proves fiddly
    the asymmetry narrows.
- **Fix B**: Make Phase 3 self-sufficient — differentiate the three kinds without new assets.
  - Strength: The must-have never depends on a later phase at all; Phase 6 degrades to a
    pure polish upgrade that is honestly cuttable.
  - Tradeoff: Needs a differentiation mechanism inside Phase 3 (Leaflet `divIcon`/CSS, or
    per-kind sizing), which is new surface in the phase the plan deliberately kept to
    payload-plus-loop — and CSS-driven markers sit awkwardly against the design system.
  - Confidence: MEDIUM — workable, but it widens the phase the plan wanted narrow, and
    `divIcon` was not verified against the existing anchor geometry.
  - Blind spot: Whether a CSS-only distinction survives the design system's "no icon
    library, plain text labels" constraints.
- **Decision**: **FIXED** via Fix A — Phase 6 and Phase 5 swapped so the markers phase runs ahead of the backfill; `*(cuttable)*` dropped from it, with the PRD must-have reasoning recorded in its Overview; Implementation Approach, Progress indices (5.1-5.7 / 6.1-6.8), the four cross-references and `plan-brief.md` all updated.

### F2 — Phase 3 retires three context keys their consumers only drop in Phase 4

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 3 §4 (`plan.md:485-488`) vs. Phase 4 §1-2
- **Detail**: Phase 3's contract says "The keys `track`, `stats` and `track_file_available`
  are retired — the template reads them per stage now." But the template edit is Phase 4.
  In the intervening commit:
  - `trip_detail.html:41` is `{% if track %}`, and it wraps **both** the Route block
    (`:42-92`) *and* the Stats block (`:103-149`). With `track` gone the gate goes falsy and
    the whole page falls to the `{% else %}` empty state at `:150` — every trip detail page
    renders "no route" while holding stages.
  - `{% if map_config %}` (`:44`) is *nested inside* that gate, so `#map` and the
    `json_script` element are not rendered either. Phase 3's own criterion 3.9 ("`#map`'s
    markup is byte-identical to today") therefore **cannot pass**, and
    `tests/trips/test_trip_detail_map.py:60` (`assert '<div id="map">' in body`) goes red.
  - Three test files assert the retired keys and are not in Phase 3's file list:
    `tests/trips/test_trip_detail.py:109,134`, and `tests/gpx/test_gpx_upload.py:343`
    (which is listed in neither Phase 3 nor Phase 4).

  Separately, `trip_detail.html:159,174` say "Replace the route" / "Replace GPX file" until
  Phase 4, so Phase 2 ships add-semantics under replace copy — the same `lessons.md` #11
  shape the plan correctly applies to the view docstrings. This breaks the standing rule
  that each step leaves the codebase in a working, committable state, and contradicts the
  plan's own framing of Phase 3 as an independently shippable widening.
- **Fix A ⭐ Recommended**: Keep the three legacy keys populated through Phase 3 as a
  declared interim shim.
  - Strength: Three lines in each view (`track` = first ordered stage's track,
    `stats`/`track_file_available` from that stage), a comment naming Phase 4 as their
    removal point, and Phase 3 stays a pure payload+client change with every existing test
    green — including 3.9 and the byte-exact `#map` pin. Phase 4 then deletes the shim in
    the same edit that stops reading it.
  - Tradeoff: The keys live on for one commit with a slightly dishonest meaning (the
    *first* stage, not "the" track), so the comment is load-bearing rather than decorative.
  - Confidence: HIGH — Phase 2 already resolves exactly this value (`plan.md:336-337`), so
    the shim is a rename, not new logic.
  - Blind spot: Does not fix the "Replace the route" copy; move that string change into
    Phase 2 alongside `success_message`, where the semantics actually flip.
- **Fix B**: Merge Phases 3 and 4 into one phase.
  - Strength: No interim state to reason about at all; the payload, the client loop and the
    template that consumes them land together, which is arguably their true atomic unit.
  - Tradeoff: Produces the largest and riskiest commit in the change — payload shape,
    `map.js`, the biggest template diff, the palette amendment and the stats correctness fix
    at once. It also loses the plan's deliberate separation of "payload is the test
    boundary" from "drawing is verifiable only by eye".
  - Confidence: MEDIUM — it works, but it trades a clean review boundary for the
    convenience of skipping a shim.
  - Blind spot: Whether the merged phase's success criteria stay individually attributable
    when a failure appears.
- **Decision**: **FIXED** via Fix A — Phase 3 §4 now keeps the three keys as a documented interim shim resolved from `stages[0]`, with the exact breakage it avoids spelled out; Phase 4 §1 retires it in both views alongside the template; the three stranded test assertions are named in Phase 4 §3; the "Replace the route" copy moved to Phase 2, where the semantics flip.

### F3 — Phase 3 silently invalidates the risk-#3 mutation shape and reddens CI's credibility gate

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 3 §2/§4; `tests/mutations.py:130-146` (unmentioned in any phase)
- **Detail**: The existing `file_always_available` shape is the **only** shape covering risk
  #3, and both of its coordinates are destroyed by Phase 3:

  ```
  module_path="trips.views"                                              # :136
  attribute="track_file_is_available"                                    # :137
  fragment='assert response.context["track_file_available"] is False'    # :145
  ```

  Its comment states the mechanism precisely: "`trips/views.py` does `from gpx.availability
  import track_file_is_available`, so the view's live reference is
  `trips.views.track_file_is_available` — patching `gpx.availability.track_file_is_available`
  would leave the view untouched." Phase 3 moves that call into `build_stages` in the new
  `gpx/stages.py` (`plan.md:444-447`), so `trips.views` stops importing the name — the patch
  target ceases to exist — and it retires the `track_file_available` context key, so the
  guard's assertion expression no longer contains the fragment.
  `tests/test_suite_bites.py:139-183` asserts the guard goes red *for the named reason*, so
  `pytest -m bite_proof` fails, which is CI's `Suite credibility` step. Nothing in any phase
  mentions `tests/mutations.py` except to *add* a new shape.
- **Fix**: Add `tests/mutations.py` to Phase 3 §4's file list: repoint `file_always_available`
  at `gpx.stages` / `build_stages`' live reference to `track_file_is_available`, and update
  `fragment` to a distinctive substring of the rewritten per-stage guard assertion in
  `tests/trips/test_trip_detail.py`. Add a Phase 3 success criterion asserting
  `pytest -m bite_proof` still passes — Phase 3 currently has no bite-proof criterion at
  all, which is why this went unseen.
- **Decision**: **FIXED** — split across both phases, which is more precise than the fix as written: Phase 3 §7 repoints `module_path` to `gpx.stages` and rewrites the re-export comment (the patch target breaks in Phase 3), while Phase 4 §3 requotes `fragment` (the shim keeps the assertion valid until Phase 4). Each phase gained its own `bite_proof` criterion (3.16, 4.13).

### F4 — `started_at__isnull=True` is not a valid null probe: untimed rows never converge

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 5 §2 (`plan.md:661-663`) and §3 (`plan.md:672-674`)
- **Detail**: Migration `0003` filters `distance_meters__isnull=True` and justifies that
  choice at `gpx/migrations/0003_backfill_gpxtrack_stats.py:44-46` — it is the only
  statistic **never legitimately null**. There is no such column among the new instants: the
  plan's own both-or-neither rule guarantees `started_at` stays null forever for an untimed
  file, and both canonical fixtures are untimed. For migration `0005` this is merely
  wasteful (one pass). The real defect is Phase 5 §3, which widens the management command's
  default filter to "rows missing *either* statistics or instants": every untimed track is
  then permanently pending, re-parsed from storage on every run, and the tally never reaches
  zero. That destroys the command's only signal for "nothing left to do" — and this command
  is the documented recovery path for a `0005` that ran against a misconfigured
  `MEDIA_ROOT`. It is the same failure class as E-05's restore drill: a step that reports
  success and converges on nothing.
- **Fix A ⭐ Recommended**: Leave the command's default filter on
  `distance_meters__isnull=True`; document `--all` as the instants-refill path.
  - Strength: No schema change, keeps `0003`'s precedent intact, and `--all` already exists
    and already means "reprocess every row" — precisely the semantics the `MEDIA_ROOT`
    recovery story needs. The default filter keeps converging.
  - Tradeoff: An operator refilling only instants must reprocess everything; at this repo's
    row count (production measured 4 rows, `roadmap.md` E-11) that is free.
  - Confidence: HIGH — it removes the non-converging predicate without adding surface.
  - Blind spot: Phase 5's manual step 5.7 ("the tally matches the row count") needs
    rewording to name which invocation it applies to.
- **Fix B**: Add a third state — a nullable "instants evaluated" marker column.
  - Strength: Makes "we looked and there was nothing" distinguishable from "we never
    looked", so a default filter can converge honestly and a future
    rider-supplied-timestamps feature has a real signal to read.
  - Tradeoff: A whole extra column and migration to encode a fact only the backfill path
    cares about — and it contradicts the plan's own "the nullable columns this change adds
    are the whole schema requirement" (`plan.md:120-121`, echoing `roadmap.md:127`).
  - Confidence: MEDIUM — correct but disproportionate at this scale.
  - Blind spot: Interaction with the both-or-neither invariant on the admin change form,
    where the pair is hand-editable.
- **Decision**: **FIXED** via Fix A — the command's default filter stays `distance_meters__isnull=True` with the non-convergence trap and the E-05 precedent recorded; `--all` documented as the instants-refill path; `0005` keeps `started_at__isnull=True` with a note on why that is sound for a one-shot migration only; `STATS_FIELDS`' role corrected so it no longer implies the filters derive from it. Criteria and Progress rows 6.4/6.7 reworded to assert convergence.

### F5 — Delete-confirmation copy is singular and sits in no phase

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: no phase; `trips/templates/trips/trip_confirm_delete.html:19-20` and
  `tests/trips/test_trip_delete.py:47-61`
- **Detail**: Behind `{% if trip.tracks.exists %}` the page says "Its GPX file will be
  deleted too." — singular, and after this change a five-stage trip loses five files to that
  one sentence. The template's own comment calls it "the part a rider cannot re-derive: a
  name and a date can be retyped, an uploaded GPX file cannot", so the wording is deliberate
  and load-bearing, not filler. Its only automated check is
  `tests/trips/test_trip_delete.py:47-61`, whose docstring says so explicitly, and it matches
  on a `GPX_WARNING` constant pinning the exact string. Neither file appears in any phase.
  This is the sole gap found against the PRD guardrail that "existing trips … edit and delete
  flows are unchanged" (`prd.md:112-113`) — unchanged behaviour, newly wrong copy.
- **Fix**: Add both files to Phase 4 §1 (the phase that already owns rider-facing stage
  wording): pluralise conditionally against the stage count, and update `GPX_WARNING` plus
  the trackless-trip guard test in step with it.
- **Decision**: **FIXED** — new Phase 4 §2 owns `trip_confirm_delete.html:19-20` and its guard test, pluralising against the stage count and keeping the trackless branch discriminating both ways; following subsections renumbered §3/§4; criterion and Progress row 4.14 added.

### F6 — Phase 2 omits the fragment-discrimination verification §6.8 requires

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §4 (`plan.md:346-353`) and criterion 2.9
- **Detail**: `test-plan.md` §6.8 makes the discrimination check mandatory, in terms that
  pre-refute the plan's criterion: "a clean unmutated pass proves nothing, since a passing
  run prints no source at all and every fragment is trivially absent from it", and "A shape
  whose guard stays green, or goes red for an unrelated reason, is a broken shape — do not
  commit it un-verified." The prescribed step is to force the guard to fail for the *wrong*
  reason and confirm the fragment stays absent from the `>`/`E ` lines. Phase 2's contract
  says only that `fragment` is "a distinctive string from that test's assertion message",
  and criterion 2.9 is just "the bite-proof harness passes". Both stop exactly where §6.8
  says proof begins — and the shape being added guards risk #1, permanent file loss.
- **Fix**: Add the §6.8 negative-verification step to Phase 2 §4's contract and a matching
  criterion (2.13): the fragment is absent from the guard's failure output when the guard is
  broken for an unrelated reason. Also reproduce §6.8's
  `.using(schema_editor.connection.alias)`, `.iterator()` and `apps.get_model` elements of
  the `0003` precedent in Phase 5 §2, which currently names only four of the seven.
- **Decision**: **FIXED** — Phase 2 §4 now carries both halves of `test-plan.md` §6.8's verification (positive under the mutation, negative for an unrelated failure), plus the factory and node-id-form details; criterion and Progress row 2.13 added. The finding's second clause (`0003`'s full six-element precedent) was applied while fixing F4.

### F7 — `build_trip_stats`' docstring claims a mirror Phase 3 breaks

- **Severity**: 💬 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 §3; `gpx/statistics.py:30-31`
- **Detail**: The module docstring asserts "`build_trip_stats` mirrors
  `gpx/map_config.py`'s `build_map_config` exactly — same `GpxTrack | None` in, same 'or
  `None` when there is nothing to show' out". Phase 3 changes `build_map_config` to
  `Sequence[Stage] -> dict | None`, so half that claim becomes false while
  `build_trip_stats` deliberately keeps its single-track signature (`plan.md:447-448`).
  `gpx/statistics.py` is in no phase's file list. This is `lessons.md` #11 — an overclaiming
  docstring is worse than an absent one.
- **Fix**: Add the one-line docstring correction to Phase 3 §3's contract, naming the
  surviving half of the mirror (the `None`-when-nothing-to-show discipline) and dropping the
  input-type claim.
- **Decision**: **FIXED** — Phase 3 §3 gains `gpx/statistics.py` (docstring only), naming the surviving half of the mirror claim and asking the implementer to confirm rather than assume that `gpx/availability.py:1-8` survives unedited.
