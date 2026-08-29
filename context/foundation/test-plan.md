# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-08-29

## 1. Strategy

Tests follow three non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic visual diff that already catches
   the regression.
2. **User concerns are first-class evidence.** Risks anchored in "the owner
   is worried about X, and the failure would surface somewhere in `<area>`"
   carry the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.

Hot-spot scope used for likelihood weighting: `accounts/`, `trips/`, `gpx/`,
`velo_log/` — excluding `context/`, `tests/`, migrations, docs,
`staticfiles/`, and vendored assets. 75 commits in the 30 days to
2026-08-29; ample signal.

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|---|---|---|---|
| 1 | Deleting or replacing a trip's track leaves its file on the volume forever — or removes a file that is still in use | High | High | interview Q2 (already burned here), interview Q3 (self-reported lowest-confidence area); roadmap E-11; `lessons.md` #10; hot-spot dir `gpx/` — 52 file-touches/30d |
| 2 | A logged-in user reaches another user's trip, or downloads their track file | High | Medium | PRD Guardrails ("under any circumstance") and Access Control; interview Q4; hot-spot dirs `trips/` — 26/30d, `gpx/` — 52/30d |
| 3 | A trip's row survives but its track becomes unreachable — the page still shows statistics while the file is gone, and nobody notices for months | High | Medium | PRD Guardrail "Data never lost"; interview Q1 (the failure is *silent*, which is what makes it the top fear); hot-spot dir `gpx/` — 52/30d |
| 4 | A regression reaches production with every gate green | High | Medium | `lessons.md` #1, #3, #4 — all three record this having already happened; roadmap E-01, E-02 |
| 5 | A malformed or hostile upload returns a server error instead of a clean rejection, and may leave a row or a file behind | Medium | Medium | PRD FR-004; PRD Non-Functional Requirements ("silent failures … are not acceptable"); hot-spot dir `gpx/` — 52/30d |
| 6 | The trip detail page breaks instead of degrading — no track, absent statistics, or an unrenderable map yields a blank or broken page | Medium | Medium | PRD Business Logic (a trip with no file is a valid empty draft); US-01 acceptance criteria; PRD Non-Functional Requirements; hot-spot dirs `trips/templates/trips/` — 22/30d, `trips/` — 26/30d |
| 7 | A deployment stores uploads somewhere the next redeploy erases | High | Low | `AGENTS.md` Hard Rules; roadmap E-05 (the restore drill found three documented steps that reported success and recovered nothing); PRD Guardrail "Data never lost" |

Risk #2 is the abuse-lens row: authorization/ownership, not merely
authentication. Risk #7 is High × Low — the platform itself is not testable
from pytest, but the *guard* that refuses a misconfigured media root is, and
that guard is the only thing standing between the owner and Risk #1's
consequence at deploy scale.

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|---|---|---|---|---|---|
| #1 | A trip removed through any path leaves nothing behind on the volume, and a surviving trip's file is never collected | That a passing deletion test proves deletion at all — a post-commit side effect asserted before the commit passes vacuously | Every path that removes or supersedes a track row, and which of them bypass model signals entirely | integration | Asserting a receiver fired instead of asserting the file is gone |
| #2 | Every trip and track route returns not-found to a second logged-in user, not only to an anonymous one | That anonymous-redirect coverage implies ownership coverage — they are different failures with different causes | The full route inventory, and whether not-found or forbidden is the contract (not-found avoids disclosing existence) | integration, parametrized over routes × actors | Testing three routes and declaring the guardrail covered |
| #3 | A trip whose file is missing from storage renders a deliberate error state and never claims success | That statistics rendering means the file is present — statistics are stored columns, deliberately decoupled from the file | What the detail view and the download path do when storage misses | integration with a storage-miss fixture | Only exercising the happy path where row and file agree |
| #4 | The suite goes red when the behavior a test names is actually broken | Coverage percentage as evidence of protection — `lessons.md` #3 and #4 record it being exactly the opposite | Which existing tests assert only a status code, and what a cost-proportionate credibility gate looks like for a solo repo | a gate (mutation-style spot check or assertion audit) | Adding tests to raise coverage rather than to catch a named regression |
| #5 | Empty, truncated, non-GPX, and oversized uploads all yield the user-facing error state, with no row and no file left behind | That "the parser raised" equals "the request was handled" — the debris question is separate from the rejection question | The rejection contract and where the transaction boundary sits relative to the storage write | unit for parsing, integration for the request | Copying the expected message out of the implementation under test (**oracle problem**) |
| #6 | A trip with no track, and one with absent statistics, both render a deliberate empty state | That a 200 means the page is usable — the requirement forbids a blank page, not merely a server error | Which template branches exist for an absent map and absent statistics | integration asserting the empty-state marker | Status-code-only assertions — `lessons.md` #1 verbatim |
| #7 | A misconfigured media root is refused rather than silently accepted | That the check works because it exists — the restore drill found three documented steps that reported success and did nothing | The guard's actual trigger conditions, and what the suite must prove with no environment file present | unit on settings resolution, integration on the probe | Testing the hosting platform instead of testing the guard |

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|---|---|---|---|---|---|
| 1 | Data-isolation contract | Prove no route lets one user read, modify, or delete another user's trip or track | #2 | integration (route × actor matrix) | implementing | `context/changes/testing-data-isolation-contract/` |
| 2 | File lifecycle and storage/row consistency | Prove every delete and replace path reclaims exactly what it should — asserted after commit, not before | #1, #3 | integration (commit-callback aware), management-command | not started | — |
| 3 | Rejection and degradation | Prove bad input and absent data produce deliberate states, never a server error or a blank page | #5, #6 | unit (parsing) + integration (view/template) | not started | — |
| 4 | Environment guard | Prove a media-root misconfiguration is refused rather than silently accepted | #7 | unit + integration on the health probe | not started | — |
| 5 | Gate credibility | Prove the suite actually goes red when the behavior it names breaks | #4 | gate (mutation-style or assertion audit) | not started | — |

Ordering rationale: Risk #1 is the only High × High row, yet Phase 1 goes to
Risk #2 first. Phase 1 is the cheapest phase, the most likely to surface a
live gap, and it depends on nothing but the route list — whereas Phase 2
cannot be written well until research has grounded the file-lifecycle
machinery. Phase 5 is last because gate credibility cannot be measured
before the tests it would measure exist.

## 4. Stack

The classic test base for this project. AI-native tools (if any) carry a
`checked:` date so future readers can see which lines need re-verification.

| Layer | Tool | Version | Notes |
|---|---|---|---|
| unit + integration | pytest + pytest-django | 9.1.1 / 4.14.0 | `testpaths = ["tests"]`; 25 test files across `tests/accounts/`, `tests/trips/`, `tests/gpx/` and the root. Test base profile: **meaningful** — this rollout closes gaps, it does not bootstrap |
| coverage | pytest-cov | 7.1.0 | Over `accounts`, `trips`, `gpx`, `velo_log`; `fail_under = 80`, `branch = true` |
| framework under test | Django | 6.0.5 | SQLite; suite runs in-memory, and must pass with no environment file present |
| domain parsing | gpxpy | 1.6.2 | Two of its calls answer `0` where a caller would read "not recorded" — presence needs its own probe |
| post-commit side effects | `django_capture_on_commit_callbacks` | pytest-django 4.14.0 | The fixture that makes Phase 2 possible; without `execute=True` a deletion assertion passes while proving nothing. checked: 2026-08-29 |
| e2e | none yet | — | Not proposed by any rollout phase. The primary flow is a small number of server-rendered pages; Phases 1–3 reach every step of it at the integration layer for a fraction of the cost |
| (optional) AI-native | assertion-audit reviewer — checked: 2026-08-29 | n/a | Candidate for Phase 5 only, weighed against classic mutation testing. **When NOT to use**: anywhere a deterministic check already answers the question. It is a judgement layer over test *quality*, never a substitute for an assertion |

**Stack grounding tools (current session):**
- Docs: Context7 — verified the `django_capture_on_commit_callbacks` contract (`using`, `execute`, and its incompatibility with `transaction=True`) against pytest-django's own `docs/helpers.md` before relying on it in §2 and §3; checked: 2026-08-29
- Search: Exa.ai — available, not used. Every stack fact needed came from the lockfile or primary docs; checked: 2026-08-29
- Runtime/browser: Playwright MCP — **not available in current session**. Browser automation exists only as a local `claude-in-chrome` skill, which is interactive and not a CI gate. This is one reason no rollout phase proposes e2e; checked: 2026-08-29
- Provider/platform: Linear MCP available (issue tracking only, no quality-gate relevance). No GitHub MCP in session — CI gate facts were read from the workflow file and `AGENTS.md`; checked: 2026-08-29

## 5. Quality Gates

The full set of gates that must pass before a change reaches production.
"Required after §3 Phase `<N>`" means the gate is enforced once that rollout
phase lands; before that, the gate is planned.

| Gate | Where | Required? | Catches |
|---|---|---|---|
| vendored-asset integrity | CI (`gates`, first step) | required | a tampered or drifted vendored asset, before anything is installed |
| lint + format + import order | local + CI | required | syntactic and style drift |
| strict typing | local + CI | required | type drift |
| migration guard | CI | required | a model change shipped without its migration — invisible to every other gate |
| collectstatic | CI | required | an unresolvable static reference; must precede the test step, which skips itself without a manifest |
| unit + integration | local + CI | required | logic regressions |
| ownership/isolation matrix | CI | required after §3 Phase 1 | one user reaching another user's data |
| post-commit side-effect assertions | CI | required after §3 Phase 2 | file-lifecycle regressions that a pre-commit assertion cannot see |
| environment-guard check | CI | required after §3 Phase 4 | a media-root misconfiguration reaching a deploy |
| suite credibility gate | CI on PR | required after §3 Phase 5 | tests that stay green when the behavior they name is broken |
| e2e on critical flows | — | not planned | see §4: no phase proposes it; the primary flow is covered at the integration layer |
| pre-prod smoke | between merge and production | optional | environment-specific failures the health probe would report |

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section is filled in once
the relevant rollout phase ships; before that, the sub-section reads
"TBD — see §3 Phase `<N>`."

### 6.1 Adding a unit test

- **Location**: `tests/<app>/`, mirroring the app package under test.
- **Naming**: `test_<behavior>.py`.
- **Reference test**: TBD — see §3 Phase 3 for the parse-rejection pattern (malformed input yields a named error, not a server error).
- **Run locally**: `uv run pytest tests/<app>/test_<name>.py`.

### 6.2 Adding an integration test through the request cycle

- TBD — see §3 Phase 1 for the ownership-denial pattern (a second logged-in user is refused on every route).

### 6.3 Adding a test for a post-commit side effect

- TBD — see §3 Phase 2 for the file-reclamation pattern (a storage effect asserted *after* the commit that triggers it, never before).

### 6.4 Adding a test for an empty or degraded page state

- TBD — see §3 Phase 3 for the deliberate-empty-state pattern (absent track or absent statistics renders a marker, asserted as content rather than as a status code).

### 6.5 Adding a test for a management command

- TBD — see §3 Phase 2 for the destructive-path pattern (a reclamation command's refusal conditions and age threshold, proven before its delete path).

### 6.6 Adding a test for a settings or environment guard

- TBD — see §3 Phase 4 for the misconfiguration-refusal pattern (the guard refuses, rather than the platform being simulated).

### 6.7 Per-rollout-phase notes

(Filled in by each phase's final sub-phase — anything surprising the phase
taught that the entries above do not already carry.)

## 7. What We Deliberately Don't Test

Exclusions agreed during the rollout (Phase 2 interview, Q5). Future
contributors should respect these unless the underlying assumption changes.

- **Django admin as a product surface** — the owner is the only admin, so admin CRUD, list columns, and filters are Django's code carrying a trusted-user blast radius. Re-evaluate if a second admin account is ever created. The admin's *file-replacement* path stays tested, because it is a file-lifecycle path (Risk #1), not an admin feature. (Source: Phase 2 interview Q5.)
- **Map rendering visuals and tile fetching** — a mapping library drawing a polyline and a public basemap serving tiles are both third-party. Assert the map configuration the server hands the page; do not diff the rendered canvas or reach the tile server. Re-evaluate if the map ever becomes server-rendered. (Source: Phase 2 interview Q5; consistent with PRD Non-Goals, which state a tile outage degrades to blank tiles with the route still drawn.)
- **Django framework internals** — password hashing, ORM query correctness, CSRF, form field coercion. The framework is its own test; assert the project's rules layered on top of it. Re-evaluate on a major framework upgrade. (Source: Phase 2 interview Q5.)
- **The hosting platform itself** — volume mounting, application-server boot, and deploy mechanics belong to the deployment runbook and the health probe, not to pytest. Note this is *not* a blanket exclusion of deployment concerns: Q5 explicitly declined to exclude them, and §3 Phase 4 tests the configuration guard for exactly that reason. (Source: Phase 2 interview Q5, by exclusion.)

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-08-29
- Stack versions last verified: 2026-08-29
- AI-native tool references last verified: 2026-08-29

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
