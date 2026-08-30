---
change_id: bootstrap-ui
title: Vendor Bootstrap 5 and restyle existing templates
status: plan_reviewed
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
