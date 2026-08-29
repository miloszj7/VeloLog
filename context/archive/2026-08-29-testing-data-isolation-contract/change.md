---
change_id: testing-data-isolation-contract
title: Prove cross-user data isolation on trip and track routes
status: archived
created: 2026-08-29
updated: 2026-08-29
archived_at: 2026-08-29T21:48:50Z
---

## Notes

Open a change folder for rollout Phase 1 of context/foundation/test-plan.md: "Data-isolation contract".
Risks covered: Risk #2 — a logged-in user reaches another user's trip, or downloads their track file (PRD Guardrails "under any circumstance" + Access Control; interview Q4; hot-spot dirs trips/ 26 touches/30d, gpx/ 52 touches/30d).
Test types planned: integration, parametrized over routes x actors.
Risk response intent: prove that every trip and track route returns not-found to a SECOND LOGGED-IN USER, not only to an anonymous one. The assumption to challenge is that anonymous-redirect coverage implies ownership coverage — they are different failures with different causes. The anti-pattern to avoid is testing three routes and declaring the guardrail covered.

## Outcome

**The brief's premise was already false, and that inverted the phase.** Research found every one of the five object-scoped routes already carried a foreign-actor test asserting 404 plus a leak or persistence assertion, and `grep 403 tests/` returned nothing. Do not re-open this as a coverage gap: ownership was covered per route before this change started.

What was missing was structural, and is what the phase actually closed:

- **G1** — no test had ever issued an HTTP request at a `/media/` path. The "nothing serves that prefix" guarantee was asserted only as a settings value, which stays true after a route, a middleware or a platform handler overrides it. Now probed as a real request against a real `file.url`, as owner, second rider and anonymous.
- **G2** — nothing asserted the route *inventory*. `OBJECT_SCOPED_ROUTES` is now compared against the URLconf, so a sixth `<int:pk>` route under `trips` or `gpx` fails the suite until classified. This is the regression path Risk #2 actually runs through, since no present route is unfiltered.
- **G3** — foreign-actor coverage was GET/POST only. Every accepted and every rejected verb is now swept.
- **G4** — `/admin/` had zero non-staff and zero anonymous coverage.
- **G5** — `other_rider` was never logged in anywhere in the suite. `other_auth_client` closes the reverse direction.

Two findings that outlived the phase, both recorded in `test-plan.md` §6.7:

- `OPTIONS` returns **200**, not 404, for a non-owner — `View.options` answers from the class's verb list without reaching `get_queryset`. It gets its own cell asserting non-disclosure by comparison against a nonexistent pk. The plan had folded it into the 404 sweep; that would have been asserting a contract Django does not offer.
- The plan's own mutation check for the media probe (`urlpatterns += static(MEDIA_URL, …)`) is a **no-op under test** — `static()` returns `[]` at `DEBUG=False`, so it passes green against a genuinely leaky config. An explicit `re_path` serve route is the correct mutation, and the closer analogue of the real threat.

Also fixed in passing: the module's body helper drained `FileResponse.streaming_content` without memoizing, so any second read returned `b""` and a leak assertion searching it would have passed vacuously.
