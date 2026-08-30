---
change_id: testing-rejection-and-degradation
title: Test plan Phase 3 - rejection and degradation coverage
status: planned
created: 2026-08-30
updated: 2026-08-30
archived_at: null
---

## Notes

Open a change folder for rollout Phase 3 of context/foundation/test-plan.md: "Rejection and degradation".
Risks covered: #5 (a malformed or hostile upload returns a server error instead of a clean rejection, and may leave a row or a file behind), #6 (the trip detail page breaks instead of degrading — no track, absent statistics, or an unrenderable map yields a blank or broken page). Test types planned: unit (parsing) + integration (view/template).
Risk response intent:
- #5: prove empty, truncated, non-GPX, and oversized uploads all yield the user-facing error state, with no row and no file left behind; challenge the assumption that "the parser raised" equals "the request was handled" (the debris question is separate from the rejection question); avoid copying the expected error message out of the implementation under test (oracle problem).
- #6: prove a trip with no track, and one with absent statistics, both render a deliberate empty state; challenge the assumption that a 200 means the page is usable — the requirement forbids a blank page, not merely a server error; avoid status-code-only assertions (lessons.md #1 verbatim).
