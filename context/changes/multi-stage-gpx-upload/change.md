---
change_id: multi-stage-gpx-upload
title: Upload a second GPX file to a trip as an additional stage, merged chronologically
status: planned
created: 2026-09-02
updated: 2026-09-02
archived_at: null
---

## Notes

Roadmap slice S-01 (`context/foundation/roadmap.md`), the M-02 north star. User can upload a second (and further) GPX file to an existing trip; on the trip detail view all stages merge into one route, ordered chronologically by GPS timestamp, each stage rendered as a visually distinct segment, with distinct start/end/stage-break markers. A single-GPX v1 trip must keep rendering unchanged.

Riskiest part: `GpxUploadView.post` today resolves `.tracks.first()` and *replaces* the trip's existing track — a `pre_save` signal reclaims the superseded file on that assumption. Changing "replace" to "add" touches that upload path and its file-lifecycle signal (`gpx/signals.py`) together; getting it wrong risks losing an earlier stage's file, not just a rendering bug.

**E-10 is included in this change**, per the user's explicit call that it's connected: `Trip.date` is currently a single `DateField`, but the product's subject is a multi-day tour. The roadmap frames E-10 as blocked on a PRD amendment (FR-003, FR-007, and the Primary Success Criterion currently say "a date", singular) before splitting `Trip.date` into start/end fields. The user's instruction here is narrower than E-10's full fix: **revise the term "Date of trip" (the label/wording) when multi-day trips are enabled** — this change should at minimum address the labeling/terminology mismatch once stages make a trip span multiple days, and should surface whether the fuller E-10 field-split belongs in this change's scope or stays a separate follow-up once the PRD amendment lands.

Known unknown carried from the roadmap: a future route removing a single stage would need its own entry in `tests/test_ownership_matrix.py` — not required by this change's scope (no stage-removal capability being built), but worth naming so planning doesn't silently skip it if scope grows.
