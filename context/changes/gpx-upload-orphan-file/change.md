---
change_id: gpx-upload-orphan-file
title: Detect and reclaim unreferenced GPX files in MEDIA_ROOT
status: implemented
created: 2026-08-28
updated: 2026-08-28
archived_at: null
---

## Notes

**Superseded**: the cause and proposed fix below are the pre-framing observation this change
opened with. `frame.md` refuted both — the atomic block was never the cause — and
`context/foundation/roadmap.md`'s E-11 row now records "Original proposal refuted" and the
actual two-layer fix that shipped. Kept verbatim below as the historical record, not as a
live description of what this change built.

Roadmap Engineering Backlog **E-11** (`context/foundation/roadmap.md`), found during the
`edit-and-delete-trip` implementation review (F10).

**Item:** A GPX upload whose transaction rolls back leaves its file in storage with no row
pointing at it (`gpx/views.py:100-113`) — `super().form_valid(form)` writes the file *inside*
`transaction.atomic()`, and storage writes do not participate in the transaction. The
`post_delete` receiver can never reach such a file: it fires on deletes, not on failed
inserts, so this is the one gap in the "lifecycle owned end-to-end" claim in `AGENTS.md`.

**Proposed fix (roadmap wording, not yet a decision):** move the file write outside the
atomic block, or register a compensating rollback hook that discards the newly written file.

**Trigger (now firing):** the next time `gpx/views.py`'s upload transaction is touched — the
block's ordering was hardened by three prior review findings, so it should be reopened
deliberately rather than in passing.

Two follow-ups when this lands: fill in E-11's `Change ID` column and flip its `Status`.
