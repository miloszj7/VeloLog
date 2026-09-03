# DESIGN SYSTEM

## Project

**Working name:** VeloLog

A Django 6 web app: a trip-centric personal diary for multi-day cycling tours,
aggregating GPX tracks and trip context into a single view. Three apps —
`accounts` (registration, login/logout), `trips` (create/list/edit/delete a
user's trips), `gpx` (upload, parse, store and download a trip's GPX file,
render its route and derived statistics).

### Design Vision

The visual style should combine elements of:

- Komoot
- Strava
- Garmin Connect

while remaining cleaner and more minimalistic.

The route map is the primary feature of the application. Every layout and UI decision should support the presentation of the map and the most important ride statistics.

---

# Design Principles

## 1. Map First

The map is the most important UI element.

Desktop:

- Map occupies 60-70% of the available width.
- Information panel occupies 30-40%.

Mobile:

- Map is always the first content block.

---

## 2. Information Hierarchy

Content priority:

1. Trip name
2. Route map
3. Key statistics
4. Trip details
5. Additional information

Users should understand the trip within three seconds of opening the page.

---

## 3. Clean and Calm

The interface should be:

- Calm
- Modern
- Readable
- Outdoor and sport oriented

Avoid:

- Heavy gradients
- Neon colors
- Glassmorphism effects
- Excessive animations
- Too many visual accents

---

# Color Palette

Colors are selected to work well with the default OpenStreetMap layer.

## Primary

Outdoor-inspired green.

```css
--bs-primary: #2f5d50;
```

Usage:

- Navigation bar
- Primary buttons
- Links
- Section headings

## Secondary

```css
--color-secondary: #5f6b6d;
```

Used for secondary and supporting text.

## Accent Orange

Strava-inspired accent color.

```css
--color-accent: #f97316;
```

Usage:

- Important values
- Active filters
- Hover states
- Route highlights

Orange should remain an accent and should not exceed roughly 10% of the visible interface.

## Background

```css
--color-bg: #f8fafb;
```

## Surface

```css
--color-surface: #ffffff;
```

## Border

```css
--color-border: #e5e7eb;
```

## Text

```css
--color-text: #1f2937;
```

## Muted Text

```css
--color-text-muted: #6b7280;
```

---

# Typography

## Font Family

No external or vendored font. Use the system font stack only, so no font asset,
`<link>`, or CDN dependency is ever introduced:

```css
font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
```

## Font Sizes

```css
H1: 32px
H2: 24px
H3: 20px
Body: 16px
Small: 14px
```

## Font Weights

```css
400
500
600
700
```

Do not use 800 or 900.

---

# Implementation

## Bootstrap Delivery

Bootstrap 5.3.8 is vendored (no CDN, no build step) at `static/vendor/bootstrap/`
— compiled `bootstrap.min.css` and `bootstrap.bundle.min.js` (the bundle variant,
so `dropdown`/`tooltip` components work without a separate Popper vendor entry),
following the same vendoring pattern already established for Leaflet at
`gpx/static/gpx/vendor/leaflet/` (README + `SHA256SUMS` integrity check wired into
`.github/workflows/deploy.yml`'s `gates` job).

## Applying This Design System

The palette, typography, radius, and shadow tokens in this document are not
authored as fresh CSS — they are applied as a `:root` CSS custom-property
override layer (`static/css/theme.css`) that redefines Bootstrap's own variables
(`--bs-primary`, `--bs-body-font-family`, `--bs-border-radius`, `--bs-box-shadow`,
etc.) plus a handful of project-only custom properties (`--color-secondary`,
`--color-accent`, `--color-bg`, `--color-surface`, `--color-border`,
`--color-text`, `--color-text-muted`) that Bootstrap has no built-in variable
for. Stylesheet load order in `templates/base.html`'s `<head>` is load-bearing:
`bootstrap.min.css` → `theme.css` → `style.css`, so the override cascades after
Bootstrap's own definitions and before the project's own rules (notably `#map`'s
sizing rule, which this design system does not govern and must stay untouched).

## Templates & Static Files

- `templates/base.html` — shared chrome (navbar, Django messages, `{% block
  content %}` / `{% block scripts %}`). Project-level shared templates live in
  `templates/`; app-namespaced templates resolve via Django's `APP_DIRS`
  (`accounts/templates/accounts/`, `trips/templates/trips/`).
- `static/css/style.css` — project-level rules that are not part of this design
  system's variable layer (currently just `#map` sizing). `static/vendor/`
  holds only vendored third-party bytes, never project-authored CSS/JS.
- App-owned static assets resolve via staticfiles' `AppDirectoriesFinder`, e.g.
  `gpx/static/gpx/map.js` and `gpx/static/gpx/vendor/leaflet/`.

## Forms

Django's default widget rendering emits no `class` attribute, and this project
adds none of `django-widget-tweaks` or `django-crispy-forms` as a dependency.
Two template filters in `accounts/templatetags/form_widgets.py` bridge that gap
and must be used instead of bare `{{ field }}` / `{{ field.label_tag }}` in any
new or restyled form template:

- `{{ field|bootstrap_widget }}` — merges a `form-control` class (default,
  overridable via a filter argument) into the widget's existing `attrs`, and
  appends `is-invalid` when the field has errors. Routes through
  `field.as_widget(attrs=...)` so pre-existing attrs (e.g. a `date` field's
  `type="date"`, `aria-describedby` help-text wiring, `autofocus`) are
  preserved rather than clobbered.
- `{{ field.label_tag|bootstrap_label }}` — adds `form-label` via
  `label_tag(attrs=...)`, preserving `label_suffix` and `id_for_label`
  resolution.

Django's default error rendering emits `<ul class="errorlist">`, not
Bootstrap's `.invalid-feedback` sibling element — `static/css/style.css` carries
an alias rule so `errorlist` visually matches `.invalid-feedback` without a new
error-rendering mechanism.

---

# Layout

## Maximum Width

```css
max-width: 1440px;
```

## Spacing Scale

```css
8
16
24
32
48
64
```

## Border Radius

```css
Cards: 12px
Map: 16px
Buttons: 10px
```

## Shadows

Default:

```css
box-shadow: 0 1px 3px rgba(0,0,0,.08);
```

Hover:

```css
box-shadow: 0 4px 12px rgba(0,0,0,.12);
```

---

# Components

## Navbar

- Height: 64px
- Background: #ffffff
- Bottom border: 1px solid #e5e7eb
- Brand logo on the left
- Never use a dark navbar

## Cards

```css
background: white;
border-radius: 12px;
border: 1px solid #e5e7eb;
```

## Statistics Cards

Highlight:

- Distance
- Duration
- Average speed
- Elevation gain

Large numeric value with a smaller descriptive label.

## Buttons

Primary:

```css
background: #2f5d50;
```

Hover:

```css
background: #23463c;
```

Secondary:

```css
background: white;
border: 1px solid #d1d5db;
```

## Icons

No icon library. Do not vendor or link an external icon font/set (e.g. Bootstrap
Icons) — every icon asset is an outbound dependency the rest of this project
deliberately avoids by vendoring everything it uses. Where a symbol would help
(e.g. next to a statistic), use plain text labels instead.

## Forms

- Minimal and clean
- Input height: 44px
- Generous spacing

---

# View: Login / Signup

Templates: `accounts/templates/accounts/login.html`,
`accounts/templates/accounts/signup.html`.

Reference: Garmin Connect.

Requirements:

- Centered login card
- Maximum width: 420px
- No illustrations
- No stock photos
- Background: #f8fafb

---

# View: Trips List

Template: `trips/templates/trips/trip_list.html`.

Layout:

- Navbar
- List of trips (list-group style; no search/filter feature exists in this
  project — do not add filter UI without a corresponding view/query)

Each trip entry contains:

- Trip name
- Date
- Description

Distance and duration are per-trip GPX statistics, shown on the trip detail
page, not in the list.

Hover state:

- Subtle shadow
- Thin orange accent bar on the left side

---

# View: Trip Create / Edit

Template: `trips/templates/trips/trip_form.html` — one template for both create
and edit, branching on `form.instance.pk`. Uses the `bootstrap_widget` /
`bootstrap_label` filters above for every field, including the `date` field
(native date input, `type="date"`).

---

# View: Trip Delete Confirmation

Template: `trips/templates/trips/trip_confirm_delete.html`. Styled as a warning
card/alert with a `btn btn-danger` submit and a secondary Cancel link.

---

# View: Trip Details

Template: `trips/templates/trips/trip_detail.html`.

Content order:

1. Trip name
2. Statistics
3. Route map
4. Detailed information (GPX upload form, Edit/Delete actions)

The map, its fallback markup, and the statistics section have conditional
rendering (`map_config`, `track`, `track_file_available`, `stats`) driven by
the `gpx` app — a stored `0` statistic must render as `0`, never fall through
to a "not recorded" fallback. This design system governs presentation classes
only; it does not change these conditions or their copy.

## Map

Desktop:

```css
min-height: 650px;
```

Mobile:

```css
min-height: 400px;
```

The map should be visible immediately when opening the page.

## Route Styling

```css
color: #f97316;
weight: 5;
outline: 2px solid white;
```

The route must remain highly visible on the default OpenStreetMap basemap.

### Stage Route Palette

A multi-stage trip draws each stage in its own colour, cycled from `STAGE_COLORS` in
`gpx/constants.py`:

```
#f97316  accent orange (stage 1 — the accent colour above, unchanged)
#2563eb  blue
#16a34a  green
#dc2626  red
#9333ea  purple
#0891b2  teal
```

This is a bounded exception to "do not introduce additional colors" below: these hues are
permitted **only** for map polylines and their matching stage-list colour swatches, never
for interface chrome (buttons, badges, links, backgrounds). The `weight: 5` / white outline
spec above is unchanged for every stage.

---

# Responsive Rules

Breakpoint:

```css
992px
```

Below this size, switch to a single-column layout.

Content order:

- Map
- Statistics
- Trip details
- Additional information

---

# AI Generation Rules

When generating HTML and CSS:

- Use the vendored Bootstrap 5.3.8 at `static/vendor/bootstrap/` — never a CDN
  link, never a different version
- Follow this Design System exactly; rely on `theme.css`'s variable overrides
  rather than hardcoding hex values in templates
- Render every form field through `{{ field|bootstrap_widget }}` /
  `{{ field.label_tag|bootstrap_label }}` (see Forms above) — never bare
  `{{ field }}` in a styled template
- Do not introduce additional colors, except the bounded Stage Route Palette exception
  under Route Styling (map polylines and their stage-list swatches only)
- Do not use gradients
- Do not use glassmorphism
- Do not implement dark mode unless explicitly requested
- Do not use an icon library — plain text labels only
- Do not load external fonts — system font stack only
- Do not add an inline `<script>` block to `templates/base.html` — the Bootstrap
  bundle script tag must stay `src=`-external with an empty body
- Keep layouts clean and spacious
- Treat the map as the primary visual element; never add a class to `#map` or
  its direct fallback `<p>` — only wrap them in an outer element
- Use orange only as an accent color
- Prioritize readability and outdoor/sports aesthetics
