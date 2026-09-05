# Refresh test-plan.md for the Playwright e2e layer — Plan Brief

> Full plan: `context/changes/test-plan-refresh-2026-09-05/plan.md`
> Research: `context/changes/test-plan-refresh-2026-09-05/research.md`

## What & Why

`context/foundation/test-plan.md` still describes e2e testing as "none yet" /
"not planned," written when no Playwright session was available. Commit
`1a2b5ff` landed a real, working, isolated Playwright layer under
`tests/e2e/`. This change refreshes test-plan.md's four stale sections (§2,
§4, §5, §8) so the document matches the codebase, without promoting e2e to a
required CI gate or adding a new top-N risk.

## Starting Point

`tests/e2e/` exists and works: an isolated `package.json` (separate from the
root Railway-IaC one), `playwright.config.ts` with a `storageState`-based
`auth.setup.ts` and a `webServer` that boots the Django dev server, and a
committed `seed.spec.ts` verified red-then-green on a deliberate break.
`.github/workflows/deploy.yml` has zero e2e references — it is not a CI gate
today. A second spec, `gpx-upload.spec.ts`, exists in the working tree but is
**not yet committed**.

## Desired End State

A reader of test-plan.md sees an accurate e2e story: a real, narrow-slice
Playwright suite exists, backed by a committed example test, explicitly not a
required gate, and documented as a supplementary protection layer on Risk #1
(file lifecycle) and Risk #6 (rendered-page degradation) — without any claim
the codebase contradicts.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Uncommitted `gpx-upload.spec.ts` | Docs-only refresh; don't cite it by path, cite `seed.spec.ts` as the committed anchor | Keeps this change purely documentation, matching change.md's scope and one-topic-per-commit | Plan |
| Manual e2e-user provisioning | Note briefly in §4 Notes column | `auth.setup.ts` has no seed fixture — a future reader needs to know a real DB user must pre-exist | Plan |
| §8 Freshness Ledger | Add one new, narrowly-scoped line for the e2e fact | Precise — doesn't imply the whole stack table was re-reviewed this session | Plan |
| Risk #1/#6 e2e placement | Prose paragraph below the §2 table, not a table-cell edit | Preserves "Likely cheapest layer" as still `integration`; e2e is supplementary, not a replacement | Plan |
| New top-N risk row | None added | change.md explicit: this is a protection layer on #1/#6, not a new risk | Research (change.md) |
| Promote e2e to required gate | No | change.md explicit out-of-scope item; confirmed true today (`deploy.yml` has no e2e step) | Research |

## Scope

**In scope:**
- §2 Risk Response Guidance — one new paragraph (Risk #1/#6 e2e note)
- §4 Stack — e2e row rewrite + Stack-grounding-tools bullet correction
- §5 Quality Gates — e2e row rewrite ("narrow slice only")
- §8 Freshness Ledger — one new scoped line
- Header "Last updated" date bump

**Out of scope:**
- Committing `tests/e2e/gpx-upload.spec.ts`
- Promoting e2e to a required CI/`lefthook.yml` gate
- Map/tile visual e2e testing (§7 stays as-is)
- Opening a new §3 rollout phase
- Re-dating stack facts unrelated to e2e

## Architecture / Approach

Single-file, single-pass documentation edit. Four sections updated in
document order in one phase; every sentence traces directly to a fact
already gathered in `research.md` (no new codebase research required to
write the prose).

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Refresh test-plan.md | §2/§4/§5/§8 updated, header date bumped | Overclaiming — a sentence stating something the codebase doesn't actually show |

**Prerequisites:** None — all facts needed were gathered during research.
**Estimated effort:** ~1 short session, single phase, no code.

## Open Risks & Assumptions

- Assumes `gpx-upload.spec.ts` stays uncommitted through this change's
  archival; if it gets committed before this lands, the "docs-only, cite
  seed.spec.ts only" framing may be worth revisiting (not required, just an
  option).
- No automated docs linter is wired into this repo's gates, so verification
  leans on manual read-through plus targeted `grep` checks rather than a
  tool-enforced pass.

## Success Criteria (Summary)

- Every claim in the refreshed §2/§4/§5/§8 traces to `tests/e2e/*` or
  `.github/workflows/deploy.yml`.
- No new top-N risk row; Risk #1/#6 table cells unchanged; §7 untouched.
- The stale "none yet" / "not planned" / "Playwright MCP not available"
  framing is fully gone from the document.
