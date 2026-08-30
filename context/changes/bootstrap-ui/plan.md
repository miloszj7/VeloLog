# Vendor Bootstrap 5 and Restyle Templates — Implementation Plan

## Overview

Vendor Bootstrap 5.3.8 (compiled CSS + JS bundle, no build step) into the project the
same way Leaflet is already vendored, wire it into `templates/base.html`, and restyle
all 8 existing templates (login, signup, trip list, trip create/edit, trip detail +
map, delete confirm) with Bootstrap classes. This is a UI polish pass — no new routes,
models, or business logic — over a project where every roadmap slice (S-01–S-05) is
already shipped.

## Current State Analysis

- `templates/base.html` is bare HTML: a plain `<header>` with a logout form, an
  unstyled `<ul>` for Django messages, and `{% block content %}` / `{% block scripts %}`
  with no wrapper.
- `static/css/style.css` carries exactly one rule (`#map` sizing) — the two prior
  slices deliberately kept the project at "no CSS" until the map required it.
- All 7 app templates (`accounts/templates/accounts/{login,signup}.html`,
  `trips/templates/trips/{trip_list,trip_form,trip_detail,trip_confirm_delete}.html`)
  render plain semantic HTML with zero classes.
- Leaflet is vendored at `gpx/static/gpx/vendor/leaflet/`, with `README.md` documenting
  *why* each sibling file (including `.map` files) must be vendored — Whitenoise's
  `CompressedManifestStaticFilesStorage` raises `MissingFileError` on any reference it
  cannot resolve, which is a boot outage per `railway.json`'s `&&`-chain ahead of
  gunicorn. A `SHA256SUMS` file beside it is checked by `.github/workflows/deploy.yml`'s
  `gates` job, first step, before `uv sync`.
- `tests/test_static_references.py` parametrizes every static path the project
  references (`STATIC_REFERENCES`) against `finders.find`, plus one manifest-render
  test against the real `trip_detail.html`.
- The test suite asserts **exact, bare markup** in far more places than a first pass
  suggests — 18 sites across 6 files, not 4. Each is a per-phase constraint below:
  - `tests/trips/test_trip_creation.py:96` — `<a href="...">Cancel</a>`
  - `tests/trips/test_trip_delete.py:69` — `<a href="...">Cancel</a>`
  - `tests/trips/test_trip_edit.py:48,51` — `<h1>Edit trip</h1>` and the Cancel anchor
  - `tests/trips/test_trip_detail_stats.py:23` (`STATS_HEADING`, used at lines 61, 145,
    165) — `<h2>Stats</h2>`
  - `tests/trips/test_trip_creation.py:185-186` — pins `id="id_date_helptext"` and
    `aria-describedby="id_date_helptext"`, the accessibility contract `trip_form.html:24-34`
    documents. Only routing through `field.as_widget(attrs=...)` preserves it; a
    hand-written `<input>` destroys it.
  - `tests/trips/test_trip_detail_map.py` (not previously in this inventory, and not yet
    in Phase 5's pytest invocation):
    - `:29` `MAP_CONTAINER = re.compile(r'<div id="map">(?P<inner>.*?)</div>', re.DOTALL)`,
      and `:60`/`:223` `assert '<div id="map">' in body` — **any class added to `#map`
      breaks all three.**
    - `:85-88` uses `MAP_CONTAINER` to assert the `"map-fallback"` text is inside the div —
      wrapping the fallback `<p>` in an inner wrapper div breaks this (non-greedy regex).
    - `:106-131` whole-page invariant: every `<script>` must be either `src=`-external or
      `type="application/json"`, with an empty body. Bootstrap's bundle tag satisfies this,
      but **any inline initializer added to `base.html` (tooltip/popover bootstrapper,
      theme toggle) fails the build.**
    - `:170` `assert "leaflet" not in body.lower()` — a full-body scan, survives class
      additions but not text changes.
    - `:26` `MAP_CONFIG_SCRIPT` pins attribute order on the map config script tag.
  - Attribute-only `href="..."` assertions that survive a class addition but break if the
    anchor markup is restructured: `test_trip_delete.py:79`, `test_trip_edit.py:65-66`,
    `test_trip_detail.py:110,136`, `test_trip_list.py:70-71`, `tests/gpx/test_gpx_upload.py:335`.
  - Confirmed clean: `tests/accounts/*` has zero markup assertions — login and signup can
    be restyled freely.
- No form-rendering library exists anywhere in the project (`grep` for
  `widget_tweaks`/`crispy` returns nothing); Django's default widgets render with no
  `class` attribute, so Bootstrap's `form-control`/`form-label` classes cannot be added
  by editing templates alone without a small helper.
- `change.md`'s "must not require any change to the CI/deploy pipeline" constraint is
  **deliberately overridden** for this change (confirmed with the user): a new CI
  integrity-check step is added for the vendored Bootstrap bytes, mirroring the existing
  Leaflet one. `change.md` is updated to record this as a conscious decision, not an
  oversight.

## Desired End State

Every page in the app (login, signup, trip list, trip create/edit, trip detail, delete
confirm) renders through Bootstrap 5.3.8 — a navbar, a `.container`-wrapped content
area, styled forms, a list-group trip list, and dismissible alerts for Django messages —
while the Leaflet map keeps rendering exactly as before (same `#map` sizing rule, same
fallback markup, same `map_config`/`stats` gating logic, untouched). The full test suite
passes, `collectstatic` completes cleanly, and the new vendored assets pass their own
CI integrity check.

**Verification**: `uv run pytest --cov` is green; `uv run python manage.py
collectstatic --noinput` completes with no `MissingFileError`; a manual pass at desktop
and ~375px mobile width shows sane layout on all 8 pages with no console errors.

### Key Discoveries:

- `trip_detail.html`'s `{% block scripts %}` (lines 158-163) **fully replaces** the
  base block rather than extending it — Django block inheritance overrides unless a
  child calls `{{ block.super }}`. Bootstrap's JS bundle must therefore load *outside*
  any overridable block in `base.html`, or the trip detail page silently loses navbar
  functionality while every other page keeps it.
- `#map`'s CSS (`static/css/style.css`) uses `vh`/`min-height`/`max-height`, none of
  which Bootstrap's utility classes touch — a wrapping `<div class="mb-4">` around the
  existing `#map` div is purely additive. (Not `<div class="container ...">` — Phase 2
  already wraps all of `{% block content %}` in `.container`, so a nested `.container`
  here would double the gutter padding; `mb-4` is spacing-only and matches Phase 5's
  own example.)
- `trip_form.html`'s create/edit branching (`form.instance.pk`) and the exact-string
  Cancel anchor test already document that this template's markup is asserted
  byte-for-byte in tests — the same care applies to every template touched here.
- Django's `SuccessMessageMixin` is the only message producer in the codebase (level
  `SUCCESS`, tag `"success"`); no `messages.error(...)` call exists anywhere. Bootstrap's
  `alert-success` class matches Django's default `"success"` tag directly, so no
  `MESSAGE_TAGS` settings override is needed for current usage.

## What We're NOT Doing

- No new Python dependency (no `django-widget-tweaks`, no `django-crispy-forms`) — a
  small in-repo template filter covers the one thing Django's default widgets can't do
  (add a CSS class).
- No changes to `forms.py` in any app, no changes to views, no changes to URLs.
- No changes to `#map`'s own CSS rule or to `gpx/map.js`/`gpx/map_config.py`.
- No dark mode, no custom Sass build, no CSS variable theming beyond Bootstrap's
  defaults — this is a "wire it in and apply classes" pass, not a design system.
- No `MESSAGE_TAGS` override — deferred until an `ERROR`-level message actually exists.
- No changes to `railway.json`, `manage.py`, or any settings file.

## Implementation Approach

Vendor Bootstrap first (Phase 1) so every later phase has real classes to reach for.
Build the shared form-styling filter alongside the base layout (Phase 2), since three
of the remaining four template phases depend on it. Then restyle template-by-template
in the order a rider actually moves through the app (auth → list/create → detail/delete),
updating the exact-markup test assertions in the same phase as the template that breaks
them — never batched separately, so each phase stays independently committable and
green.

## Critical Implementation Details

- **Script placement in `base.html`**: the Bootstrap JS bundle (`bootstrap.bundle.min.js`)
  must be a plain `<script>` tag in `base.html` itself, placed *before* `{% block
  scripts %}` and not inside it — see "Key Discoveries" above. `{% block scripts %}`
  stays exactly as it is today, reserved for page-specific scripts (Leaflet).
- **Widget class injection**: Django's `BoundField.__str__` calls `as_widget()` with no
  attrs. Bootstrap's `form-control` class is added via a new template filter
  (`{{ field|bootstrap_widget }}` replacing bare `{{ field }}`) that merges a `class`
  attribute into the widget's existing `attrs` — this must preserve `TripForm`'s
  `date` field's `attrs={"type": "date"}` and not clobber it.

## Phase 1: Vendor Bootstrap 5.3.8

### Overview

Add the compiled Bootstrap CSS + JS bundle under a new project-level vendor directory,
following the exact documentation/integrity pattern `gpx/static/gpx/vendor/` already
establishes for Leaflet, and wire the new CI check + static-reference test entries.

### Changes Required:

#### 1. Vendored asset files

**File**: `static/vendor/bootstrap/bootstrap.min.css`, `bootstrap.min.css.map`,
`bootstrap.bundle.min.js`, `bootstrap.bundle.min.js.map`

**Intent**: The compiled, minified Bootstrap 5.3.8 distribution (MIT licence), fetched
from the official `dist/` build (e.g. `unpkg.com/bootstrap@5.3.8/dist/`). The bundle JS
variant is used (not the base `bootstrap.js`) so `dropdown`/`tooltip` components work
without a separate Popper vendor entry, matching the "vendor everything a component
might need" posture Leaflet already set.

**Contract**: Byte-identical to the upstream release; `.map` files vendored alongside
their `.js`/`.css` for the same reason Leaflet's is (the source-mapping comment is a
static reference Whitenoise's manifest storage must resolve).

#### 2. Vendor documentation

**File**: `static/vendor/bootstrap/README.md`

**Intent**: Mirror `gpx/static/gpx/vendor/README.md`'s structure exactly — version,
source URL, licence, a per-file "why is this here" table, an "Upgrading" section with
the `sha256sum` regeneration command, and the checksum table reproduced for
readability.

**Contract**: Same document shape as the Leaflet README; the "Upgrading" section names
`static/vendor/bootstrap/` as its own working directory.

#### 3. Integrity checksums

**File**: `static/vendor/bootstrap/SHA256SUMS`

**Intent**: `sha256sum` output for the 4 vendored files, generated the same way
Leaflet's is (`cd static/vendor/bootstrap && sha256sum *.css *.css.map *.js *.js.map >
SHA256SUMS`), run *after* verifying the downloaded bytes against the upstream release.

**Contract**: One line per file, same format as `gpx/static/gpx/vendor/SHA256SUMS`.

#### 4. CI integrity gate

**File**: `.github/workflows/deploy.yml`

**Intent**: Add a second "Vendored asset integrity" step for Bootstrap, immediately
after the existing Leaflet one, so a tampered or truncated Bootstrap asset fails the PR
before `uv sync` the same way a bad Leaflet asset does. This is the documented,
deliberate deviation from `change.md`'s original "no CI/deploy pipeline change"
constraint.

**Contract**: A new step with `working-directory: static/vendor/bootstrap` running
`sha256sum -c SHA256SUMS`, named distinctly from the Leaflet step (e.g. "Vendored asset
integrity (Bootstrap)") so a failure's origin is unambiguous in CI logs.

#### 5. Change identity record (verification only)

**File**: `context/changes/bootstrap-ui/change.md`

**Intent**: `change.md:20-25` already records that the "no CI change" constraint was
deliberately overridden, with the reason (parity with the existing Leaflet integrity
check) — written during `/10x-plan`. This step is a verification, not an edit: confirm
the note is present before proceeding; do not append a second copy.

**Contract**: No edit unless the note is missing, in which case add it once to the
`## Notes` section.

#### 6. Static-reference test coverage

**File**: `tests/test_static_references.py`

**Intent**: Add the two new static paths to the `STATIC_REFERENCES` tuple so
`finders.find` coverage extends to Bootstrap, matching how the four Leaflet paths are
already covered.

**Contract**: Two new literal entries — `"vendor/bootstrap/bootstrap.min.css"` and
`"vendor/bootstrap/bootstrap.bundle.min.js"` — appended to the existing tuple.

#### 7. Line-ending pin

**File**: `.gitattributes`

**Intent**: This machine has `core.autocrlf=true`, and the existing pin only covers
`gpx/static/gpx/vendor/**`. Without a matching rule for the new vendor path, git
CRLF-converts the vendored Bootstrap files on checkout, so a `SHA256SUMS` generated
locally fails `sha256sum -c` on CI's Linux checkout — the exact reason the Leaflet
vendoring commit (`a48a5d6`) shipped its `.gitattributes` rule in the same commit.

**Contract**: Add `static/vendor/** -text` to `.gitattributes`, committed before or
together with the vendored bytes (run `git add --renormalize static/vendor` if the
bytes were already staged/committed without the rule). Generate `SHA256SUMS` (item 3)
only after this rule is in effect, so the checksums are taken over the byte-identical,
unconverted files.

### Success Criteria:

#### Automated Verification:

- `sha256sum -c SHA256SUMS` passes in both `gpx/static/gpx/vendor` and
  `static/vendor/bootstrap`
- `uv run python manage.py collectstatic --noinput` completes with no
  `MissingFileError`
- `uv run pytest tests/test_static_references.py --cov` passes

#### Manual Verification:

- `static/vendor/bootstrap/README.md` reads as a faithful parallel to the Leaflet one
- The new CI step's name makes an integrity failure's origin obvious from the Actions
  log alone
- `git check-attr text -- static/vendor/bootstrap/bootstrap.min.css` reports `unset`,
  matching the Leaflet vendor path

---

## Phase 2: Base layout, navbar, and shared form-styling filter

### Overview

Wire Bootstrap into `base.html` (navbar, container, styled messages) and add the
template filter every later form-styling phase depends on.

### Changes Required:

#### 1. Base template

**File**: `templates/base.html`

**Intent**: Load Bootstrap's CSS in `<head>` (before `style.css`, preserving the
existing override-order comment), add a Bootstrap navbar replacing the bare `<header>`.
The navbar and brand (linking to the trip list) render on every page, authenticated or
not — this is a behavior change from today, where the whole `<header>` is gated on
`user.is_authenticated`. Only the logout button stays gated on `user.is_authenticated`,
preserving today's behavior for the control that actually matters (an anonymous user
must never see or be able to trigger logout). Wrap `{% block content %}` in a
`.container my-4`, and move the Django messages block inside that container (so alerts
aren't full-bleed) rendering them as dismissible Bootstrap alerts
(`alert alert-{{ message.tags }} alert-dismissible fade show`, with a `btn-close`
button). Load `bootstrap.bundle.min.js` as a plain `<script>` tag placed before
`{% block scripts %}` — see Critical Implementation Details above for why it cannot go
inside that block.

**Contract**: `{% block content %}` and `{% block scripts %}` keep their existing
names/positions relative to each other so no child template needs to change its
`{% block %}` declarations; only what wraps them changes. The Bootstrap script tag
must be a plain `src=`-external `<script>` with an empty body — no inline
initializer (tooltip/popover bootstrapper, theme toggle, etc.) anywhere in
`base.html`. `tests/trips/test_trip_detail_map.py:106-131` asserts, page-wide, that
every `<script>` is either `src=`-external or `type="application/json"` with no body;
an inline `<script>` block added here fails that test on the trip-detail page even
though this phase never touches that file directly.

#### 2. Form-styling template filters

**File**: `accounts/templatetags/__init__.py` (new package),
`accounts/templatetags/form_widgets.py` (new)

**Intent**: Two filters. `bootstrap_widget`, that every form template's field loop
calls instead of bare `{{ field }}`. It merges a `class` (default `"form-control"`,
overridable via a filter argument) into the field's existing widget `attrs`, and
appends `is-invalid` when `field.errors` is non-empty — without touching any
`forms.py`. `bootstrap_label`, called instead of bare `{{ field.label_tag }}`, adds
`form-label` to the rendered `<label>`. Housed in `accounts` as the most neutral of
the three apps (no domain coupling to `trips`/`gpx` models); template tag libraries
are loadable from any template regardless of which installed app defines them.

**Contract**:

```python
@register.filter(name="bootstrap_widget")
def bootstrap_widget(field: BoundField, css_class: str = "form-control") -> str:
    ...

@register.filter(name="bootstrap_label")
def bootstrap_label(field: BoundField) -> str:
    return field.label_tag(attrs={"class": "form-label"})
```

`bootstrap_widget` must preserve any attrs already on the widget (e.g. `TripForm`'s
`date` field's `attrs={"type": "date"}`, and `AuthenticationForm`'s `autofocus` on
username / `autocomplete="current-password"` on password) rather than replacing the
whole `attrs` dict — route through `field.as_widget(attrs=...)`, which merges
correctly and preserves the `aria-describedby` stamped by `build_widget_attrs`; never
assign `widget.attrs = {...}` directly. `bootstrap_label` must go through
`label_tag(attrs=...)`, not hand-written `<label>` markup — templates cannot pass
arguments to a bare `{{ field.label_tag }}` call (Django always invokes it with
`attrs=None`), and a hand-written `<label>` would silently drop `label_suffix`
handling (removing the trailing ":" from every label) and bypass `id_for_label`
resolution, with no test catching either regression. Do not use
`Form.required_css_class` as a shortcut — it only fires for required fields, so
`Trip.description` (`blank=True`) would be missed.

#### 3. Filter unit tests

**File**: `tests/accounts/test_form_widgets.py` (new)

**Intent**: This is new branching Python logic (default vs. argument class, errors
vs. no errors), not a styling change, and `pyproject.toml`'s `branch = true` coverage
setting means it lands both branches uncovered unless tested here directly — the
Testing Strategy's "no new unit tests for pure styling changes" does not apply to it.
Cover: existing widget attrs survive (`type="date"` present alongside
`form-control`), the default class applies, the argument override applies, and
`is-invalid` appears only when `field.errors` is non-empty.

**Contract**: At least 4 test cases as listed above; each asserts against a real
`BoundField` (constructed from a minimal test form), not a mock.

#### 4. Error-text styling alias

**File**: `static/css/style.css`

**Intent**: Django's default error rendering emits `<ul class="errorlist">`, not
Bootstrap's expected sibling `.invalid-feedback` element — so `is-invalid` alone only
recolors the input border and leaves the error text itself unstyled. Add one rule
aliasing `errorlist`'s appearance to Bootstrap's `.invalid-feedback` (color, font
size, margin) so the two form ecosystems visually match without introducing a new
error-rendering mechanism.

**Contract**: CSS-only change; no template or Python edit. Must not affect the
`#map` rule already in this file.

### Success Criteria:

#### Automated Verification:

- `uv run mypy .` passes with the new `templatetags` module fully typed
- `uv run pytest tests/accounts/test_form_widgets.py --cov` passes, covering both
  filters' branches (no template uses them yet, so `pytest --cov` on the rest of the
  suite is a regression check on `base.html` alone)
- `uv run python manage.py collectstatic --noinput` succeeds

#### Manual Verification:

- Every page shows the new navbar and container spacing
- A test message (e.g. trigger "Trip saved.") renders as a dismissible green alert with
  a working close button
- Logout button still only appears for authenticated users, and still logs out via POST
- `#map`'s existing sizing rule in `style.css` is unaffected by the new `errorlist`
  alias rule

---

## Phase 3: Auth templates (login, signup)

### Overview

Restyle the two auth templates using the Phase 2 filter and Bootstrap form/card
markup.

### Changes Required:

#### 1. Login template

**File**: `accounts/templates/accounts/login.html`

**Intent**: Wrap the form in a Bootstrap card, apply `bootstrap_widget` to each field
and `bootstrap_label` to each `field.label_tag`, keep the existing "Need an account?
Sign up" link and hidden `next` field exactly as they behave today (no test currently
asserts their markup verbatim, only their behavior via redirects).

**Contract**: Field loop structure (`{% for field in form %}`) stays; only the classes
applied to label/widget/wrapper change.

#### 2. Signup template

**File**: `accounts/templates/accounts/signup.html`

**Intent**: Same treatment as login.html.

**Contract**: Same as above.

### Success Criteria:

#### Automated Verification:

- `uv run pytest tests/accounts --cov` passes unchanged (these tests assert substrings
  like `"Please enter a correct username and password"` and `reverse("logout")`, not
  exact markup, so no test edits are needed)
- `uv run black --check .`, `uv run ruff check .`, `uv run isort --check-only .` pass

#### Manual Verification:

- Login and signup forms render as centered Bootstrap cards with visible labels,
  `form-control` inputs, and a styled submit button
- An invalid login attempt shows `is-invalid` styling on the affected field(s) and the
  error text itself is styled to match Bootstrap's `.invalid-feedback` look (via the
  Phase 2 `errorlist` alias), not left as unstyled default text
- Both pages are usable at ~375px width with no horizontal scroll

---

## Phase 4: Trip list and trip create/edit form

### Overview

Restyle the trip list as a Bootstrap list-group and the create/edit form using the
shared filter, then update the 3 test assertions that hardcode the bare Cancel anchor.

### Changes Required:

#### 1. Trip list template

**File**: `trips/templates/trips/trip_list.html`

**Intent**: Replace the bare `<ul>`/`<li>` with a Bootstrap `list-group`, each trip as
a `list-group-item` carrying name, date, and description; the empty-state `<li>` stays
a plain list-group-item with its existing copy unchanged (`test_trip_list.py` asserts
substrings like `"haven't logged any trips"`, not exact markup, so no test edits are
needed here).

**Contract**: `{% for trip in object_list %}...{% empty %}...{% endfor %}` structure
unchanged; only wrapping element classes change.

#### 2. Trip form template

**File**: `trips/templates/trips/trip_form.html`

**Intent**: Apply `bootstrap_widget` to each field (including the `date` field, whose
existing `type="date"` attrs must survive), `bootstrap_label` to each
`field.label_tag`, and `form-text` styling to the existing help-text `<div>`, style
the submit button
(`btn btn-primary`) and the Cancel link as a Bootstrap secondary button/link
(`btn btn-outline-secondary` or `link-secondary`) — whichever the implementer picks,
the resulting anchor must still carry `href="{{ ... }}"` and the text `Cancel` so the
updated test substring match (below) stays meaningful.

**Contract**: The `{% if form.instance.pk %}` create/edit branching stays exactly as
today; only classes are added to the elements already there.
`tests/trips/test_trip_creation.py:185-186` pins `id="id_date_helptext"` and
`aria-describedby="id_date_helptext"` on the date field — this accessibility
contract, documented at `trip_form.html:24-34`, survives only if the field is routed
through `field.as_widget(attrs=...)` (i.e. the `bootstrap_widget` filter); a
hand-written `<input>` for the date field breaks it.

#### 3. Cancel-anchor test updates

**File**: `tests/trips/test_trip_creation.py`, `tests/trips/test_trip_delete.py`,
`tests/trips/test_trip_edit.py`

**Intent**: Replace the 3 exact bare-tag assertions (`<a href="...">Cancel</a>`) and
the 1 exact `<h1>Edit trip</h1>` assertion with substring checks tolerant of added
attributes — e.g. assert `f'href="{url}"'` and `>Cancel<` appear in the body, and that
`"Edit trip"` appears inside an `<h1` tag, rather than reconstructing the whole tag.

**Contract**: Each updated assertion must still fail if the link's `href` or the
heading's text changes — only the tolerance for added attributes changes, not what's
being proven.

### Success Criteria:

#### Automated Verification:

- `uv run pytest tests/trips/test_trip_creation.py tests/trips/test_trip_delete.py tests/trips/test_trip_edit.py tests/trips/test_trip_list.py --cov` passes with the updated assertions
- `uv run mypy .`, `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .` pass

#### Manual Verification:

- Trip list renders as a styled list-group with a visible "New trip" call-to-action
- Create and edit forms render with styled fields, the date picker's native widget
  still works, and the help text under the date field is visible and styled
- Cancel navigates to the same destination as before (list when creating, trip detail
  when editing)

---

## Phase 5: Trip detail, GPX upload form, and delete confirmation

### Overview

Restyle the remaining two templates without disturbing the map's own container/CSS or
any of its conditional fallback branches, then update the `<h2>Stats</h2>` assertions.

### Changes Required:

#### 1. Trip detail template

**File**: `trips/templates/trips/trip_detail.html`

**Intent**: Wrap the page's sections (trip header/actions, route/map, stats, GPX
upload form) in Bootstrap spacing/card classes. The `#map` div and its inner fallback
`<p class="map-fallback">` keep their `id`/class exactly as-is — only an outer wrapper
gains Bootstrap classes (e.g. `<div class="mb-4">` around the existing `<h2>Route</h2>`
and its sibling `#map`/fallback block). Style the stats `<dl>` with Bootstrap's `row`/
`col` grid (implementer's choice of exact grid classes, as long as each `<dt>`/`<dd>`
pair's existing conditional text is unchanged) and the GPX upload form with the Phase
2 filter. Edit/Delete links become styled buttons.

This deliberately reverses the "no class, no styling" decision recorded in
`trip_detail.html:86-88` (kept there so the stats section stays readable with the
stylesheet blocked) — replace that comment with a short note that the section is now
styled and relies on Bootstrap loading rather than staying stylesheet-independent.
Confirmed with the user as an intentional reversal, not an oversight.

**Contract**: Every existing `{% if %}` branch (`map_config`, `track`,
`track_file_available`, `stats`) keeps its exact condition and exact fallback copy —
this phase adds wrapping/classes only, never new conditions or reworded copy. The
`{% block scripts %}` Leaflet script tags are untouched (Phase 2 already accounted for
Bootstrap's JS loading outside this block). This is load-bearing, not incidental:
`tests/trips/test_trip_detail_map.py:29,60,223` byte-match `<div id="map">` with no
attributes, and `:85-88`'s non-greedy `MAP_CONTAINER` regex breaks if the fallback
`<p>` gains an inner wrapper — so `#map` and its direct fallback `<p>` must stay
completely unclassed, exactly as the "outer wrapper only" instruction above already
requires.

#### 2. Delete confirmation template

**File**: `trips/templates/trips/trip_confirm_delete.html`

**Intent**: Style as a Bootstrap alert/card warning about the destructive action, with
a `btn btn-danger` submit button and a plain `link-secondary` Cancel link.

**Contract**: The `{% if trip.tracks.exists %}` conditional warning stays exactly as
today; only classes are added.

#### 3. Stats-heading and zero-vs-null test updates

**File**: `tests/trips/test_trip_detail_stats.py`

**Intent**: Replace the `STATS_HEADING = "<h2>Stats</h2>"` exact-match constant with a
substring check tolerant of an added class (e.g. `"Stats</h2>"` combined with an
`<h2` presence check, or a regex), used identically at its 3 call sites. Also rewrite
the two negative assertions guarding the zero-vs-null distinction —
`:110 assert "<dd>0 min</dd>" not in body` and `:126 assert "<dd>0 m</dd>" not in
body` — as positive assertions tolerant of an added class on `<dd>` (e.g. assert the
exact recorded value appears inside a `<dd` tag, still distinct from the
not-recorded fallback copy). A class added to `<dd>` makes the current negative form
vacuously true instead of red, silently deleting the guard `trip_detail.html:91-98`
and `AGENTS.md` document (a stored `0` must render as "0", never fall through to the
"not recorded" fallback).

**Contract**: The updated heading check must still distinguish "the Stats heading is
present" from "the Stats heading is absent" exactly as the 3 existing call sites
(present, present, absent) require. The rewritten zero-vs-null assertions must still
fail if a real `0` value ever renders as the not-recorded fallback text (prove this
by temporarily reverting the fix and confirming the test goes red, then restoring
it).

### Success Criteria:

#### Automated Verification:

- `uv run pytest tests/trips/test_trip_detail.py tests/trips/test_trip_detail_map.py tests/trips/test_trip_detail_stats.py tests/trips/test_trip_delete.py --cov` passes
- `uv run pytest tests/gpx --cov` passes unchanged (no gpx test asserts trip_detail
  markup beyond what's already covered above)
- `uv run mypy .`, `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .` pass

#### Manual Verification:

- The Leaflet map still renders and sizes correctly (60vh/18rem/40rem bounds intact) on
  a trip with a route
- The map-unavailable, track-file-unavailable, and stats-not-recorded fallback messages
  still render with their exact existing copy, now inside styled containers
- Delete confirmation clearly reads as a destructive action (danger-colored button)
- The rewritten zero-vs-null stats assertions still go red when a real `0` value is
  made to render as the not-recorded fallback (verified by temporary revert)

---

## Phase 6: Full-suite verification and cross-page visual QA

### Overview

Confirm the whole app is consistent after 5 template-touching phases, at both desktop
and mobile widths, with every gate green.

### Changes Required:

No further file changes are expected in this phase — it is verification-only. If the
manual pass surfaces an inconsistency (e.g. a missed unstyled element), fix it in the
template it belongs to and re-run that phase's automated checks before proceeding.

### Success Criteria:

#### Automated Verification:

- `uv run pytest --cov` passes in full (fail_under = 80 maintained)
- `uv run python manage.py collectstatic --noinput` succeeds
- `uv run python manage.py check` passes
- `uv run mypy .`, `uv run ruff check .`, `uv run black --check .`, `uv run isort --check-only .` all pass
- `sha256sum -c SHA256SUMS` passes in both vendor directories

#### Manual Verification:

- All 8 pages (login, signup, trip list, trip create, trip edit, trip detail with a
  route, trip detail with no route, delete confirm) visually reviewed at desktop width
  and at ~375px width, with no horizontal scroll and no broken layout
- Browser console shows no JS errors on any page
- The full golden path (register → log in → create a trip → upload a GPX file → see
  the route drawn) still works end-to-end through the restyled UI

---

## Testing Strategy

### Unit Tests:

- No new unit tests are added for pure styling changes; existing tests are updated
  only where they assert exact markup that styling necessarily changes (Phases 4–5).

### Integration Tests:

- The existing `test_the_trip_detail_page_renders_under_the_production_static_storage`
  manifest-render test (in `tests/test_static_references.py`) continues to exercise the
  one page with every kind of static reference, now including Bootstrap's.

### Manual Testing Steps:

1. Run the dev server and walk the golden path end-to-end at desktop width.
2. Resize the browser (or use device emulation) to ~375px and repeat.
3. Trigger a validation error on login and on the trip form; confirm `is-invalid`
   styling and the error text both appear.
4. Trigger the "Trip saved."/"Trip updated." success messages and dismiss them via the
   alert's close button.

## Performance Considerations

Bootstrap's minified CSS/JS adds a fixed, cacheable payload (~230KB combined,
uncompressed) on top of the existing Leaflet vendor bundle — served with the same
content-hashed, long-cache manifest storage as every other static asset, so this is a
one-time cost per browser, not a per-page-load one.

## Migration Notes

Not applicable — no data model or schema changes.

## References

- Vendoring precedent: `gpx/static/gpx/vendor/README.md`, `gpx/static/gpx/vendor/SHA256SUMS`
- CI precedent: `.github/workflows/deploy.yml` "Vendored asset integrity" step
- Change identity: `context/changes/bootstrap-ui/change.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Vendor Bootstrap 5.3.8

#### Automated

- [ ] 1.1 `sha256sum -c SHA256SUMS` passes in both vendor directories
- [ ] 1.2 `collectstatic --noinput` completes with no MissingFileError
- [ ] 1.3 `pytest tests/test_static_references.py --cov` passes

#### Manual

- [ ] 1.4 Bootstrap vendor README reads as a faithful parallel to the Leaflet one
- [ ] 1.5 New CI step's name makes a failure's origin unambiguous
- [ ] 1.6 `git check-attr text -- static/vendor/bootstrap/bootstrap.min.css` reports `unset`

### Phase 2: Base layout, navbar, and shared form-styling filter

#### Automated

- [ ] 2.1 `mypy .` passes with the new templatetags module typed
- [ ] 2.2 `pytest tests/accounts/test_form_widgets.py --cov` passes, both filters' branches covered
- [ ] 2.3 `collectstatic --noinput` succeeds

#### Manual

- [ ] 2.4 Every page shows the new navbar and container spacing
- [ ] 2.5 A success message renders as a dismissible alert with a working close button
- [ ] 2.6 Logout still only shows for authenticated users and still logs out via POST
- [ ] 2.7 `#map`'s existing sizing rule in `style.css` is unaffected by the new
      `errorlist` alias rule

### Phase 3: Auth templates (login, signup)

#### Automated

- [ ] 3.1 `pytest tests/accounts --cov` passes unchanged
- [ ] 3.2 `black --check .`, `ruff check .`, `isort --check-only .` pass

#### Manual

- [ ] 3.3 Login/signup render as styled Bootstrap cards with visible labels
- [ ] 3.4 Invalid login shows `is-invalid` field styling and the error text itself
      is styled via the `errorlist` alias, not left as unstyled default text
- [ ] 3.5 Both pages usable at ~375px width with no horizontal scroll

### Phase 4: Trip list and trip create/edit form

#### Automated

- [ ] 4.1 `pytest tests/trips/test_trip_creation.py tests/trips/test_trip_delete.py tests/trips/test_trip_edit.py tests/trips/test_trip_list.py --cov` passes with updated assertions
- [ ] 4.2 `mypy .`, `ruff check .`, `black --check .`, `isort --check-only .` pass

#### Manual

- [ ] 4.3 Trip list renders as a styled list-group with a visible "New trip" CTA
- [ ] 4.4 Create/edit forms render styled, date picker works, help text visible
- [ ] 4.5 Cancel navigates to the same destination as before in both flows

### Phase 5: Trip detail, GPX upload form, and delete confirmation

#### Automated

- [ ] 5.1 `pytest tests/trips/test_trip_detail.py tests/trips/test_trip_detail_map.py tests/trips/test_trip_detail_stats.py tests/trips/test_trip_delete.py --cov` passes
- [ ] 5.2 `pytest tests/gpx --cov` passes unchanged
- [ ] 5.3 `mypy .`, `ruff check .`, `black --check .`, `isort --check-only .` pass

#### Manual

- [ ] 5.4 Leaflet map still renders and sizes correctly on a trip with a route
- [ ] 5.5 Map/track/stats fallback messages still render with exact existing copy
- [ ] 5.6 Delete confirmation clearly reads as a destructive action
- [ ] 5.7 Rewritten zero-vs-null stats assertions still go red when a real `0` value
      is made to render as the not-recorded fallback (verified by temporary revert)

### Phase 6: Full-suite verification and cross-page visual QA

#### Automated

- [ ] 6.1 `pytest --cov` passes in full (fail_under = 80 maintained)
- [ ] 6.2 `collectstatic --noinput` succeeds
- [ ] 6.3 `manage.py check` passes
- [ ] 6.4 `mypy .`, `ruff check .`, `black --check .`, `isort --check-only .` all pass
- [ ] 6.5 `sha256sum -c SHA256SUMS` passes in both vendor directories

#### Manual

- [ ] 6.6 All 8 pages reviewed at desktop and ~375px width, no horizontal scroll/broken layout
- [ ] 6.7 No browser console JS errors on any page
- [ ] 6.8 Full golden path works end-to-end through the restyled UI
