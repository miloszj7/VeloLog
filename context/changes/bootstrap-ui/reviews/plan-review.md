<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Vendor Bootstrap 5 and Restyle Templates

- **Plan**: `context/changes/bootstrap-ui/plan.md`
- **Mode**: Deep
- **Date**: 2026-08-30
- **Verdict**: REVISE (pre-triage) → SOUND (post-triage — all 9 findings fixed)
- **Findings**: 3 critical, 4 warnings, 2 observations — all FIXED

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | WARNING |
| Architectural Fitness | WARNING |
| Blind Spots | FAIL |
| Plan Completeness | FAIL |

## Grounding

10/10 paths ✓, 6/6 symbols ✓, brief↔plan ✓, Progress↔Phase contract ✓ (34 criteria bullets, all mapped 1:1 across 6 phases; exactly one `## Progress` at the bottom; no stray checkboxes in phase bodies).

## Verified in the plan's favor

Do not re-litigate these — each was checked against source:

- Bootstrap 5.3.8 is genuinely the current release (npm `latest`), closing the brief's version risk.
- Both `.map` files are load-bearing, not merely tidy: without them `collectstatic` raises
  (`ValueError` at `django/contrib/staticfiles/storage.py:144`, re-raised by
  `collectstatic.py:152-157` under `manifest_strict = True`). Django 6.0.5 rewrites
  `sourceMappingURL` in both `*.css` (storage.py:91-95) and `*.js` (storage.py:102-104).
- Bootstrap's embedded SVG data-URIs are safe — the `url()` converter skips them
  (storage.py:225-227, `^[a-z]+:`).
- The `{% block scripts %}` key discovery is correct: `trip_detail.html:158` has no
  `{{ block.super }}`, and the plan correctly places Bootstrap's script outside the block.
- `form-control` is the right class for every field in the project. Full inventory checked:
  no checkbox, `Select`, or `RadioSelect` exists anywhere. `usable_password` lives on
  `AdminUserCreationForm` only (`django/contrib/auth/forms.py:592-594`), not on
  `BaseUserCreationForm` (:213), so `SignUpForm` is unaffected.
- A templatetag library in `accounts/templatetags/` is loadable from `trips`/`gpx`
  templates — `accounts` is in `INSTALLED_APPS` (settings.py:59) and Django scans every
  installed app's `templatetags` package. `builtins`/`libraries` are unset, so an explicit
  `{% load %}` is required in each template.
- `tests/test_coverage_scope.py` only guards top-level `INSTALLED_APPS` packages, so a new
  `accounts/templatetags/` subpackage needs no `pyproject.toml` change.

## Findings

### F1 — Phase 1 omits the .gitattributes pin, breaking its own CI gate

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 (plan.md:114-196) — all six enumerated artifacts
- **Detail**: This machine has `core.autocrlf=true`. `.gitattributes` contains exactly one
  rule — `gpx/static/gpx/vendor/** -text` — which does not cover the plan's new
  `static/vendor/bootstrap/` path. Verified directly:

  ```
  $ git check-attr text -- static/vendor/bootstrap/bootstrap.min.css
    text: unspecified          ← will be CRLF-converted on checkout
  $ git check-attr text -- gpx/static/gpx/vendor/leaflet/leaflet.css
    text: unset                ← protected
  ```

  All four Bootstrap files are NUL-free text, so git converts them. `SHA256SUMS` generated
  on this Windows box (Leaflet's carries the `*` binary-mode prefix, so that is how it is
  done here) then fails `sha256sum -c` on CI's Linux checkout — Phase 1's own automated
  criterion 1.1, and the new CI gate the phase adds.

  The precedent the plan cites made this explicit. Commit `a48a5d6`, which vendored
  Leaflet, shipped `.gitattributes` in the *same commit*: "The accompanying .gitattributes
  keeps the vendored bytes identical to the published release. Without it this machine's
  line-ending conversion would rewrite the stylesheet on checkout, so the same commit would
  produce different asset names on a developer's machine than in production."

  Phase 1 enumerates six artifacts and claims to mirror "the exact documentation/integrity
  pattern" — but misses the seventh, which is the one making the pattern hold cross-platform.
- **Fix**: Add a 7th item to Phase 1 — extend `.gitattributes` with `static/vendor/** -text`,
  committed before or with the vendored bytes. If the bytes land first, `git add --renormalize`
  is required. Generate `SHA256SUMS` only after the pin is in effect.
- **Decision**: FIXED — added item 7 to Phase 1, a manual verification bullet, and Progress 1.6.

### F2 — The exact-markup test inventory is incomplete (4 listed, ~18 real)

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Plan Completeness
- **Location**: Current State Analysis (plan.md:31-37); Phases 4-5
- **Detail**: plan.md:31 asserts "Four places in the test suite assert exact, bare markup".
  That inventory is what Phases 4 and 5 derive their test-update lists from, and what the
  implementer trusts to know where to be careful. The four listed are all real and correctly
  quoted. At least 14 more exist.

  The three that matter most are in `tests/trips/test_trip_detail_map.py` — a file the plan
  never mentions:

  ```
  :29   MAP_CONTAINER = re.compile(r'<div id="map">(?P<inner>.*?)</div>', re.DOTALL)
  :60   assert '<div id="map">' in body
  :223  assert '<div id="map">' in body
  :85-88 uses MAP_CONTAINER to assert "map-fallback" is inside it
  ```

  Any class on `#map` breaks :60 and :223; the non-greedy regex also means wrapping the
  fallback `<p>` in an inner div breaks :87. Phase 5's contract (plan.md:414-417) happens to
  forbid both — but by luck of wording, not because these tests were known. An implementer
  styling a "map card" has nothing telling them `#map`'s tag is asserted byte-exact.

  ```
  :106-131  whole-page invariant: EVERY <script> must be either src=-external or
            type="application/json", with an empty body.
  ```

  Bootstrap's bundle tag passes this — but any inline initializer added to `base.html`
  (a tooltip/popover bootstrapper, a theme toggle) fails the build.

  Also unlisted: `tests/trips/test_trip_creation.py:185-186` pins `id="id_date_helptext"`
  and `aria-describedby="id_date_helptext"` — the accessibility contract that
  `trip_form.html:24-34` documents at length. A filter routed through
  `field.as_widget(attrs=...)` preserves it; any hand-written `<input>` destroys it.

  Lower-risk but unlisted: `test_trip_detail_map.py:170` (`assert "leaflet" not in body.lower()`,
  a full-body scan), `:26` (`MAP_CONFIG_SCRIPT` pins attribute order), and attribute-only
  `href="..."` assertions in `test_trip_delete.py:79`, `test_trip_edit.py:65-66`,
  `test_trip_detail.py:110,136`, `test_trip_list.py:70-71`, `tests/gpx/test_gpx_upload.py:335`
  (these survive a class addition but break if the anchors are restructured).

  Confirmed clean: `tests/accounts/*` has zero markup assertions — login and signup can be
  restyled freely, exactly as Phase 3 claims.
- **Fix A ⭐ Recommended**: Correct the inventory and convert it into per-phase constraints.
  - Strength: Cheap, and it puts the constraint where the implementer reads it. Phase 5
    already has the right instincts about `#map` — this makes them load-bearing rather than
    incidental, and adds `test_trip_detail_map.py` to criterion 5.1's pytest invocation,
    where it is currently absent.
  - Tradeoff: The assertions stay brittle; the next styling change re-runs this discovery.
  - Confidence: HIGH — every site quoted above was read directly.
  - Blind spot: The sweep covered angle-bracket literals; a test asserting on rendered text
    position rather than markup could still exist.
- **Fix B**: Add a Phase 0 replacing brittle string assertions with a small HTML-parsing
  assertion helper before any restyling begins.
  - Strength: Removes the class of problem. Future UI work stops being hostage to byte-exact
    markup, and the vacuous-negative traps in F4 become impossible.
  - Tradeoff: Touches ~18 assertions across 6 test files before any visible progress;
    meaningfully enlarges a "UI polish" change and risks weakening a guard while rewriting it.
  - Confidence: MEDIUM — mechanics are simple, but each rewritten assertion must be proven
    still-failing-when-it-should.
  - Blind spot: No HTML-parsing dependency exists today; this would add one, contradicting
    plan.md:82 ("No new Python dependency").
- **Decision**: FIXED — via Fix A. Corrected the markup inventory in Current State Analysis (18 sites across 6 files), added test_trip_detail_map.py constraints to Phase 5, the empty-script-body constraint to Phase 2, and the aria-describedby constraint to Phase 4.

### F3 — `form-label` is promised in 3 phases with no mechanism to apply it

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phase 2 contract (plan.md:258-266) vs. Phases 3/4/5
- **Detail**: The plan diagnoses this correctly at plan.md:38-41 — "Bootstrap's
  `form-control`/`form-label` classes cannot be added by editing templates alone without a
  small helper" — then designs a helper for only the first of the two. Phase 2's contract
  defines exactly one filter, `bootstrap_widget`. Phase 3 (plan.md:299) then instructs
  "add `form-label` to `field.label_tag`", and Phases 4-5 repeat the pattern.

  That is not possible from a template. `django/forms/boundfield.py:167`:

  ```python
  def label_tag(self, contents=None, attrs=None, label_suffix=None, tag=None):
  ```

  Django templates cannot pass arguments to a method, so `{{ field.label_tag }}` always
  calls it as `label_tag()` with `attrs=None`. `legend_tag` (:211) delegates to the same
  method and emits `<legend>`, not `<label>` — not an escape hatch.

  The likely improvisation — hand-writing `<label class="form-label" for="{{ field.id_for_label }}">`
  — silently drops the `label_suffix` handling at boundfield.py:178-189, removing the
  trailing ":" from every label across all four form templates, and bypasses the
  `id_for_label` resolution at :191-195. No test asserts label markup, so this ships green.

  Note the same triple (`{{ field.label_tag }}` / `{{ field }}` / `{{ field.errors }}`)
  appears verbatim in four places — `trip_form.html:21-39`, `trip_detail.html:144-155`,
  `signup.html:10-16`, `login.html:11-17` — so whatever mechanism is chosen is applied four times.
- **Fix**: Extend Phase 2's contract with a second filter, `{{ field|bootstrap_label }}`,
  returning `field.label_tag(attrs={"class": "form-label"})` — fully supported by the
  signature above, and preserving `label_suffix`, `for=`/`id_for_label` resolution, and
  `required_css_class`. Note for the implementer: `Form.required_css_class`
  (boundfield.py:196-201) looks like a zero-template-change shortcut but only fires for
  required fields, so `Trip.description` (`blank=True`) would be missed. Don't take it.
- **Decision**: FIXED — added `bootstrap_label` filter to Phase 2's contract, and updated Phases 3-4 to call it instead of bare `field.label_tag`.

### F4 — Restyling the stats `<dl>` reverses a documented decision and silently voids two guards

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Architectural Fitness
- **Location**: Phase 5 (plan.md:418-421)
- **Detail**: Phase 5 says "Style the stats `<dl>` with Bootstrap's `row`/`col` grid or
  `list-group` (implementer's choice)". `trip_detail.html:86-88` records the opposite
  decision in the file itself: "A definition list and nothing else — no class, no styling…
  this section has to stay readable with the stylesheet blocked, which a `<dl>` is and a
  table of bare `<div>`s is not." A `row`/`col` grid is precisely the bare-`<div>` table
  that comment rejects. The plan neither cites nor overrides it.

  Second, quieter consequence — `tests/trips/test_trip_detail_stats.py`:

  ```
  :110  assert "<dd>0 min</dd>" not in body
  :126  assert "<dd>0 m</dd>" not in body
  ```

  These are NEGATIVE assertions. A class on `<dd>` does not turn them red; it makes them
  vacuously true, silently deleting the zero-versus-null guard that `trip_detail.html:91-98`
  exists to enforce — the exact distinction `AGENTS.md` calls out ("a `0` stored there would
  render as 'no climbing' rather than as 'not recorded'"). Green suite, guard gone.
- **Fix A ⭐ Recommended**: Leave the `<dl>` and its `<dt>`/`<dd>` unclassed; apply Bootstrap
  only to the section wrapper around it.
  - Strength: Honors the recorded decision, keeps both negative assertions meaningful, and
    still delivers visible polish via the surrounding card/spacing. Bootstrap's Reboot
    already improves `<dl>` typography for free.
  - Tradeoff: Stats read as a plain definition list rather than a two-column grid.
  - Confidence: HIGH — the constraint is written in the template and the tests are quoted above.
  - Blind spot: Whether the no-CSS-fallback rationale is still binding is the user's call.
- **Fix B**: Restyle the `<dl>`, and in the same phase rewrite :110 and :126 as positive
  assertions plus update the template comment to record the reversal.
  - Strength: Full visual consistency with the rest of the page.
  - Tradeoff: Reverses a deliberate accessibility decision inside a "wire it in and apply
    classes" pass; the assertion rewrite must be proven to still fail on a real `0`.
  - Confidence: MEDIUM — mechanically fine; the design call is the user's.
  - Blind spot: Other stats assertions may share the same negative shape.
- **Decision**: FIXED — via Fix B. Phase 5 now records the reversal explicitly (template comment update), and rewrites the two negative zero-vs-null assertions as positive ones with a revert-and-verify step (Progress 5.7).

### F5 — The shared filter ships untested; its one named failure mode is checked only by eye

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 2; Testing Strategy (plan.md:506-509)
- **Detail**: Testing Strategy says "No new unit tests are added for pure styling changes".
  `bootstrap_widget` is not a styling change — it is new Python logic that three phases
  depend on, with branching (default vs. argument class, errors vs. no errors) and one
  documented way to go wrong: clobbering `TripForm`'s `attrs={"type": "date"}`
  (`trips/forms.py:23`). That is the only pre-existing widget `attrs` in the project's own
  code, but `AuthenticationForm` also ships `autofocus` on username and
  `autocomplete="current-password"` on password (`django/contrib/auth/forms.py:311,315`),
  so the merge requirement is broader than the plan states.

  Nothing automated proves the merge. The only check is manual item 4.4 ("date picker
  works"). If the filter clobbers, the date input degrades to a free-text box and the suite
  stays green — `lessons.md` #1 and #3 describe exactly this failure shape, and #1 was
  logged after a real bug reached `master` this way.

  Compounding it: `pyproject.toml:67` sets `branch = true`, so Phase 2 lands a branching
  module with zero call sites and both branches uncovered, at the very gate (criterion 2.2)
  meant to bless it.
- **Fix**: Add a sub-phase to Phase 2 — `tests/accounts/test_form_widgets.py` covering:
  existing attrs survive (assert `type="date"` present alongside `form-control`), the
  default class applies, the argument override applies, and `is-invalid` appears only when
  `field.errors` is non-empty. Four cases, and it converts criterion 2.2 from a regression
  check into a real one. Implementation note: route through `field.as_widget(attrs=...)`,
  which merges correctly (boundfield.py:85-111) and preserves the `aria-describedby`
  stamped by `build_widget_attrs`; never assign `widget.attrs = {...}`.
- **Decision**: FIXED — added tests/accounts/test_form_widgets.py sub-phase to Phase 2 (4 cases), updated criterion 2.2, and broadened the attrs-preservation contract to include AuthenticationForm.

### F6 — Phase 1 step 5 re-appends a note change.md already has

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Lean Execution
- **Location**: Phase 1 #5 (plan.md:175-186)
- **Detail**: The step instructs appending a note to `change.md` recording the deliberate CI
  override. `change.md:20-25` already contains it, written during `/10x-plan`. An implementer
  following Phase 1 literally appends a duplicate paragraph.
- **Fix**: Delete Phase 1 #5, or reword it to "verify the note at change.md:20-25 is present
  — written during planning".
- **Decision**: FIXED — reworded Phase 1 item 5 to a verification-only step.

### F7 — Navbar gating contradicts its own Progress criterion

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: End-State Alignment
- **Location**: Phase 2 (plan.md:228-237) vs. Progress 2.4 (plan.md:570)
- **Detail**: Phase 2 specifies the navbar "visible only when `user.is_authenticated` exactly
  as today" — today `base.html:21-28` gates the whole `<header>`. Progress 2.4 asserts "Every
  page shows the new navbar and container spacing", and Phase 6 reviews login and signup,
  which are anonymous pages. Under the Phase 2 reading, those two pages get no navbar and no
  brand, and 2.4 cannot pass. The plan does not say which behavior it wants.
- **Fix**: State it explicitly — render the navbar and brand always, gate only the logout
  button on `user.is_authenticated` (preserving today's behavior for the control that
  matters), and reword 2.4 to match. Also confirm the messages block moves inside the
  `.container` so alerts are not full-bleed.
- **Decision**: FIXED — Phase 2 now renders navbar/brand always, gates only the logout button, and moves the messages block inside .container.

### F8 — Key Discoveries proposes a container nested inside a container

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architectural Fitness
- **Location**: plan.md:69-71 vs. plan.md:232 and 419
- **Detail**: Key Discoveries suggests `<div class="container my-3">` around `#map`, while
  Phase 2 already wraps all of `{% block content %}` in `.container my-4`. A nested
  `.container` doubles the gutter padding — Phase 5's own example correctly uses `mb-4`.
- **Fix**: Change the Key Discoveries wording to `<div class="mb-4">` so it agrees with
  Phase 5 and cannot be copied literally.
- **Decision**: FIXED — corrected Key Discoveries wording to `mb-4` with a note explaining why `.container` would double gutter padding.

### F9 — `is-invalid` won't pair with anything Bootstrap styles

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 filter; criterion 3.4
- **Detail**: `{{ field.errors }}` renders `<ul class="errorlist" id="id_<field>_error">`
  (`django/forms/errors/list/ul.html`, default `error_class` from `django/forms/utils.py:150-158`)
  with no template-level hook for a class. Bootstrap's `is-invalid` is designed to reveal a
  sibling `.invalid-feedback`; against an `errorlist` it only recolors the input border while
  the error text stays unstyled. Criterion 3.4 ("invalid login shows error message and
  is-invalid styling") passes either way, so the mismatch will not be caught. Django already
  stamps `aria-invalid="true"` on the widget when a field has errors (boundfield.py:294-295),
  which is the natural pairing point.
- **Fix**: Accept the border-only treatment and reword 3.4 to say so, or add one CSS rule in
  `style.css` aliasing `.errorlist` to `.invalid-feedback`'s appearance. Either is fine —
  decide it now rather than mid-Phase-3.
- **Decision**: FIXED — added a Phase 2 CSS-alias sub-phase for `errorlist`, and reworded criterion 3.4/Progress 3.4 to assert the styled error text.
