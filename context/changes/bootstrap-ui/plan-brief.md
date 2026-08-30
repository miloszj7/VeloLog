# Vendor Bootstrap 5 and Restyle Templates — Plan Brief

> Full plan: `context/changes/bootstrap-ui/plan.md`

## What & Why

Vendor Bootstrap 5.3.8 (CSS + JS, no build step) into VeloLog the same way Leaflet is
already vendored, then restyle all 8 existing templates with it. All five roadmap
slices are shipped; this is a pure UI polish pass, not blocking any pending feature.

## Starting Point

Every template today is bare semantic HTML with zero CSS classes, except one rule in
`static/css/style.css` sizing the Leaflet `#map` container. There is no navbar, no
styled forms, no styled trip list — the two prior slices deliberately kept the project
at "no CSS" until the map required it.

## Desired End State

Every page — login, signup, trip list, trip create/edit, trip detail with its map and
stats, delete confirmation — renders through a Bootstrap navbar, container, styled
forms, a list-group trip list, and dismissible alerts, while the Leaflet map's sizing,
fallback states, and conditional logic are byte-for-byte unchanged.

## Key Decisions Made

| Decision | Choice | Why | Source |
|---|---|---|---|
| Bootstrap delivery | Vendored 5.3.8 CSS+JS bundle, not CDN | Matches the established Leaflet precedent (no third-party runtime dependency) | Plan |
| Vendor location | New `static/vendor/bootstrap/` (project-level) | Styles the whole app, not one Django app — mirrors the project-vs-app-owned static split in AGENTS.md | Plan |
| CI integrity check | New CI step added, deliberately overriding `change.md`'s "no CI change" constraint | Parity with the existing Leaflet `sha256sum -c` gate; user confirmed the override explicitly | Plan |
| Exact-markup test conflicts (Cancel anchors, `<h1>`, `<h2>Stats</h2>`) | Update the 4 assertion sites to tolerant substring checks | Keeps styling consistent everywhere rather than leaving 4 elements bare | Plan |
| Form field styling | New template filter (`bootstrap_widget`), no new pip dependency | Lowest-risk, template-only change; no `forms.py`/views touched | Plan |
| Navigation | Bootstrap navbar + `.container` wrapper in `base.html` | Highest-value change for perceived polish; PRD requires a responsive web app | Plan |
| Trip list | `list-group`, not a card grid | Idiomatic Bootstrap component, minimal markup restructuring (`<li>` → `list-group-item`) | Plan |
| Map wrapping | Bootstrap spacing/card classes around `#map`, `#map`'s own CSS untouched | Zero collision risk — Bootstrap utilities never touch height/width | Plan |

## Scope

**In scope:** vendoring Bootstrap, `base.html` navbar/container/alerts, a shared form
filter, restyling all 7 app templates, updating the 4 test sites whose exact-markup
assertions styling breaks, a new CI integrity step.

**Out of scope:** any `forms.py`/views/URL change, dark mode or custom theming, a new
form-rendering library, `MESSAGE_TAGS` overrides (no `ERROR`-level messages exist
today), any change to `#map`'s sizing CSS or `gpx/map.js`/`gpx/map_config.py`.

## Architecture / Approach

Bootstrap is vendored as static files, loaded from `base.html`. A small template
filter lets existing `{% for field in form %}` loops apply `form-control`/`is-invalid`
classes without touching any Python form code. Templates are restyled one at a time in
the order a rider moves through the app, each phase updating its own broken test
assertions rather than batching test fixes separately.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Vendor Bootstrap | New vendor dir, README, SHA256SUMS, CI gate, static-reference test entries | New CI step is a deliberate constraint override — must be visible, not silent |
| 2. Base layout + form filter | Navbar, container, styled alerts, `bootstrap_widget` filter | Bootstrap JS must load outside `{% block scripts %}` or `trip_detail.html` silently loses it |
| 3. Auth templates | Styled login/signup cards | Low — no exact-markup tests on these pages |
| 4. Trip list + form | list-group list, styled create/edit form | 3 Cancel-anchor tests need updating in the same phase |
| 5. Trip detail + delete confirm | Styled map wrapper, stats, upload form, delete page | Must not disturb any of the map's conditional fallback branches or exact copy |
| 6. Full-suite QA | Desktop + mobile visual pass, all gates green | Catching any missed unstyled element before calling this done |

**Prerequisites:** none — all roadmap slices are already shipped.
**Estimated effort:** ~1 session across 6 phases (styling-only, no new domain logic).

## Open Risks & Assumptions

- Bootstrap 5.3.8 is the current stable release as of this plan (verified via web
  search); if a newer patch ships before implementation, re-verify the version and
  checksums rather than assuming this number is still current.
- The `bootstrap_widget` filter's home in `accounts/templatetags/` is a judgment call
  (no app is a natural "shared utils" home in this 3-app project) — documented in the
  plan so it isn't mistaken for accidental coupling.

## Success Criteria (Summary)

- All 8 pages visibly restyled with Bootstrap, at both desktop and ~375px mobile width
- Full test suite green, `collectstatic` clean, both vendor directories pass their
  integrity checks
- The Leaflet map and its fallback states are unchanged in behavior and copy
