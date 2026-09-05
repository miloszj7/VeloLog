---
change_id: test-plan-refresh-2026-09-05
title: Refresh test-plan.md for now-available Playwright e2e layer
status: implemented
created: 2026-09-05
updated: 2026-09-05
archived_at: null
---

## Notes

Refresh context/foundation/test-plan.md: Playwright e2e infra landed (commit 1a2b5ff, tests/e2e/, seed.spec.ts, verified passing). Update:
- §4 Stack: e2e row from "none yet" to Playwright + version, testDir tests/e2e/, isolated package.json, storageState auth via auth.setup.ts, webServer boots the Django dev server.
- §5 Quality Gates: e2e row from "not planned" to "narrow slice only" — not a required CI gate, cost × signal still favors integration for ownership/lifecycle/rejection.
- §2 Risk Response Guidance: add an e2e response layer to Risk #1 (file lifecycle) and Risk #6 (rendered-page degradation) covering the one thing neither the Django test client nor an integration test reaches: a real browser multipart file-upload widget round-tripping through GpxUploadForm.clean_file into rendered stage/stats DOM, surviving a hard reload. Do not add a new top-N risk number — this is an additional protection layer on #1/#6, not a new risk.
- Explicitly out of scope: promoting e2e to a required gate; map/tile visual testing (§7 already excludes it).
