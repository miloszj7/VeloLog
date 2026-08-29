# Data-Isolation Contract — Plan Brief

> Full plan: `context/changes/testing-data-isolation-contract/plan.md`
> Research: `context/changes/testing-data-isolation-contract/research.md`

## What & Why

Rollout Phase 1 of `context/foundation/test-plan.md`, covering Risk #2: *a logged-in user reaches
another user's trip, or downloads their track file.* The PRD guardrail is absolute — "one
authenticated user can never read, modify, or delete another user's private trips under any
circumstance" — and the project's entire authorization story is a single owner-scoped-queryset
idiom, hand-copied into five views with nothing structural forcing a sixth to follow.

## Starting Point

Research inverted the brief's premise. All five object-scoped routes **already** have a
second-logged-in-user test asserting 404 plus a no-leak or persistence assertion, maintained
deliberately since S-02 and documented in view docstrings. `grep 403 tests/` returns zero hits and
no route leaks. So the coverage gap the phase was opened to close does not exist — writing eight
more per-route tests would land on the very anti-pattern the brief warns about, in a new form.

What is genuinely unproven sits in five places the existing tests structurally cannot reach:
no test ever requests a `/media/…` path (G1); nothing asserts the route *inventory* (G2);
foreign-actor verb coverage is GET/POST only while `http_method_names` is a security control here
(G3); `/admin/` has no non-staff coverage (G4); and `other_rider` is never logged in anywhere in
the suite (G5).

## Desired End State

One flat module, `tests/test_ownership_matrix.py`, holds a declared inventory of every
object-scoped route and drives a route × actor × verb matrix from it. A sixth pk-bearing route
added without a classification turns the suite red. Requesting a real stored track's `file.url`
returns 404 for the owner, a second rider, and an anonymous visitor, with the bytes absent every
time. A non-staff rider is refused at an admin object route. `AGENTS.md` carries the invariant as
a Hard Rule, and test-plan §6.2 answers "how do I add an isolation test?"

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| The contract to assert | 404 for a foreign logged-in user; 302-to-login for anonymous | All five views filter the queryset rather than fetching then comparing, so a foreign pk is indistinguishable from a nonexistent one — a 403 test would assert the wrong contract | Research |
| Phase deliverable | Close G1–G5 and add an inventory guard; leave the eight existing tests untouched | Spends the phase on what is unproven; consolidating would churn five passing files and risk losing the bespoke assertions that carry the signal | Plan |
| Guard reach | Declared tuple + a test diffing it against the URLconf's `<int:pk>` routes | Closes the "route #6 forgets the idiom" vector — the only live regression path, since no present route is unfiltered | Plan |
| `/admin/` scope | In, boundary only — non-staff and anonymous are refused | Admin is where the guarantee terminates, not an admin feature; the same reasoning §7 already uses to keep the file-replacement path tested | Plan |
| Cell strictness | Status **plus** a state/no-leak probe, every cell | A 404 alone passes against a view that did the work then refused, and cannot distinguish `gpx:download`'s three distinct 404 causes | Research + Plan |
| File layout | One flat `tests/test_ownership_matrix.py` | Matches how every cross-cutting concern is filed; the guard sits beside the tuple it guards | Plan |
| Docs | `AGENTS.md` Hard Rule + test-plan §6.2 | `AGENTS.md` loads every session and currently says nothing about access control (`lessons.md` #5); §6.2 is the phase's contracted deliverable | Plan |

## Scope

**In scope:** the route descriptor tuple and its URLconf guard; foreign-actor and anonymous cells
across every accepted verb; disallowed-verb cells for a non-owner; the reverse direction;
malformed-body-against-foreign-pk on `trips:edit` and `gpx:upload`; the `/media/` exposure probe;
two admin boundary cells; `AGENTS.md` and test-plan doc updates.

**Out of scope:** consolidating the existing eight ownership tests; refactoring the five
`get_queryset` overrides into a shared mixin (production code); admin as a product surface; any
CI work — the matrix is ordinary pytest already run by the `gates` job; Risks #1 and #3–#7
(test-plan Phases 2–5); e2e.

## Architecture / Approach

Bottom-up in one module. A module-level tuple of typed route descriptors — route name, pk object,
accepted verbs, and a **state-probe callable** — is both the matrix's parameter source and what the
introspection guard compares the URLconf against. The probe is the part a URL string cannot supply
and is what makes a cell mean anything. Two boundary probes sit outside the tuple because neither
is a route the project owns: `/media/`, whose entire defense is the *absence* of a route, and
`/admin/`, whose contract is a login redirect rather than a 404.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Inventory + guard | Route descriptor tuple, URLconf-diff guard, `other_auth_client` fixture | The guard's namespace walk misses a route shape, so it passes while proving nothing |
| 2. The matrix | Foreign / anonymous / disallowed-verb / reverse-direction / existence-oracle cells | Cells that run but do not bite — mitigated by the named mutation checks |
| 3. Boundary probes | `/media/` exposure probe (owner + foreign + anonymous), admin refusal cells | A hardcoded media path would 404 for the trivial reason and keep passing after a media route is added |
| 4. Docs + rollout state | `AGENTS.md` Hard Rule, test-plan §6.2, Phase 1 → `complete` | A rule written as a change summary rather than as an instruction |

**Prerequisites:** none — research is complete and no upstream phase blocks this.
**Estimated effort:** ~2 sessions across 4 phases; Phase 2 is the bulk.

## Open Risks & Assumptions

- **The matrix's value is entirely in whether it bites.** Each phase names a production line to
  temporarily break and the cells that must go red; these are the real acceptance criteria
  (`lessons.md` #1, #3, #4 all record a green gate concealing a real regression).
- **`LoginRequiredMixin` runs ahead of the method check**, so anonymous + a disallowed verb is 302
  and foreign + a disallowed verb is 405 — a cell written from the wrong assumption will fail.
- **The invariant is unconditional only while FR-009 (public/private trips) stays parked for v2**;
  naming it once, centrally, makes that a one-line change rather than a rewrite of every assertion.
- **Some matrix cells deliberately overlap the existing per-behavior tests.** That duplication is
  the accepted cost of keeping their bespoke assertions in place.

## Success Criteria (Summary)

- A pk-bearing route added to `trips/` or `gpx/` without an ownership classification turns the
  suite red, rather than shipping green.
- Every trip and track route refuses a second logged-in rider on every verb it accepts, with the
  refusal proven by state, not by a status code alone.
- No URL under `MEDIA_URL` serves a rider's track file to anyone — including its owner.
