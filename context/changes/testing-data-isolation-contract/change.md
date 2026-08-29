---
change_id: testing-data-isolation-contract
title: Prove cross-user data isolation on trip and track routes
status: implementing
created: 2026-08-29
updated: 2026-08-29
archived_at: null
---

## Notes

Open a change folder for rollout Phase 1 of context/foundation/test-plan.md: "Data-isolation contract".
Risks covered: Risk #2 — a logged-in user reaches another user's trip, or downloads their track file (PRD Guardrails "under any circumstance" + Access Control; interview Q4; hot-spot dirs trips/ 26 touches/30d, gpx/ 52 touches/30d).
Test types planned: integration, parametrized over routes x actors.
Risk response intent: prove that every trip and track route returns not-found to a SECOND LOGGED-IN USER, not only to an anonymous one. The assumption to challenge is that anonymous-redirect coverage implies ownership coverage — they are different failures with different causes. The anti-pattern to avoid is testing three routes and declaring the guardrail covered.
