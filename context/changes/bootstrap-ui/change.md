---
change_id: bootstrap-ui
title: Vendor Bootstrap 5 and restyle existing templates
status: implementing
created: 2026-08-30
updated: 2026-08-30
archived_at: null
---

## Notes

Vendor Bootstrap 5 (CSS + JS, no build step) into the project the same way Leaflet is
already vendored under `gpx/static/gpx/vendor/`, wire it into `templates/base.html`,
and restyle the existing templates (login/register, trip list, trip create/edit form,
trip detail + map, delete confirm) with Bootstrap classes. All five roadmap slices
(S-01–S-05) are done; this is a UI polish pass, not blocking any pending slice. Must
not regress the Leaflet map (already vendored, no build tooling) or require any change
to the CI/deploy pipeline.

**Planning decision (2026-08-30):** the "no CI/deploy pipeline change" constraint above is
deliberately overridden. Vendoring Bootstrap with the same integrity guarantee Leaflet
already has requires a new `sha256sum -c` step in `.github/workflows/deploy.yml` — confirmed
explicitly with the user during `/10x-plan` rather than silently dropping the constraint or
silently skipping Bootstrap's integrity check. See `plan.md` Phase 1 and `plan-brief.md`'s
"Key Decisions" table.

**Planning decision (2026-08-30):** a new Phase 2 ("Design-system theme layer") was
inserted after the plan's initial review, applying `context/foundation/design-system.md`
(custom color palette, system-font typography, spacing/radius/shadow tokens — no icon
library, no external font) as a CSS-variable override on top of vendored Bootstrap,
before any template is restyled. All later phases were renumbered (old Phase 2 → 3,
3 → 4, 4 → 5, 5 → 6, 6 → 7) accordingly. Status reset to `planned` pending re-review of
the updated plan. No new vendored assets, CDN links, or CI steps are introduced by this
addition — `theme.css` is a plain project-owned stylesheet, styled the same way
`static/css/style.css` already is.

**Plan review decision (2026-08-30):** `/10x-plan-review` found (F1, CRITICAL) that
Phase 2's premise — that overriding `--bs-primary` alone retheme's Bootstrap's
`-rgb`/`-text-emphasis`/`-bg-subtle`/`-border-subtle` derivatives, links, headings, and
component classes like `.btn-primary` — is factually wrong per Bootstrap 5.3's own docs;
those are independent, Sass-compile-time-baked values, not runtime derivatives of
`--bs-primary`. Fixed in place (Fix A, no strategy change): Phase 2's `theme.css`
contract now lists the complete, corrected override set (`--bs-link-color`,
`--bs-heading-color`, `--bs-focus-ring-color`, `--bs-primary-rgb`, plus a single named
`.btn-primary` component override using the exact hex already in `design-system.md`),
explicitly scopes out `-text-emphasis`/`-bg-subtle`/`-border-subtle` for `primary` as
unused by this project rather than inventing values `design-system.md` doesn't specify,
and reworded the affected Phase 2/4 success criteria to check something actually
verifiable. Still no Sass build, no new dependency — see `reviews/plan-review.md` for
the full finding and the rejected alternative (a local Sass build of Bootstrap).
