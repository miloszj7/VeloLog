---
change_id: testing-environment-guard
title: Prove the media-root misconfiguration guard refuses deploys instead of silently accepting them
status: planned
created: 2026-08-31
updated: 2026-08-31
archived_at: null
---

## Notes

Open a change folder for rollout Phase 4 of context/foundation/test-plan.md: "Environment guard".
Risks covered: #7 — a deployment stores uploads somewhere the next redeploy erases (High impact, Low likelihood; `AGENTS.md` Hard Rules, roadmap E-05, PRD Guardrail "Data never lost").
Test types planned: unit + integration on the health probe.
Risk response intent: #7 — prove a misconfigured media root is refused rather than silently accepted; must challenge "the check works because it exists" (the restore drill found three documented steps that reported success and did nothing); ground the guard's actual trigger conditions and what the suite must prove with no environment file present; likely cheapest layer is unit on settings resolution + integration on the probe; avoid testing the hosting platform instead of testing the guard.
After creating the folder, follow the downstream continuation rule: suggest /10x-research next unless blocked.
