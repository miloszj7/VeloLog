---
change_id: testing-gate-credibility
title: Prove test gates catch the regressions they claim to catch
status: archived
created: 2026-08-31
updated: 2026-09-02
archived_at: 2026-09-02T14:38:36Z
---

## Notes

Open a change folder for rollout Phase 5 of context/foundation/test-plan.md: "Gate credibility".
Risks covered: #4 (a regression reaches production with every gate green).
Test types planned: gate (mutation-style or assertion audit).
Risk response intent: #4 — prove the suite goes red when the behavior a test names is actually broken; challenge coverage percentage as evidence of protection (lessons.md #3 and #4 record it being exactly the opposite); ground which existing tests assert only a status code and what a cost-proportionate credibility gate looks like for a solo repo; avoid adding tests to raise coverage rather than to catch a named regression.
