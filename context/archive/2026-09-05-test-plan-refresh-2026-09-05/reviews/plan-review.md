<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Refresh test-plan.md for the Playwright e2e layer

- **Plan**: `context/changes/test-plan-refresh-2026-09-05/plan.md`
- **Mode**: Deep
- **Date**: 2026-09-05
- **Verdict**: SOUND (after fixes; REVISE at time of initial review)
- **Findings**: 0 critical, 3 warnings, 0 observations — all 3 fixed during triage

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING (pre-fix) |
| Plan Completeness | WARNING (pre-fix) |

## Grounding

7/7 paths ✓ (`context/foundation/test-plan.md`, `context/changes/test-plan-refresh-2026-09-05/change.md`, `tests/e2e/playwright.config.ts`, `tests/e2e/auth.setup.ts`, `tests/e2e/seed.spec.ts`, `.github/workflows/deploy.yml`, `context/foundation/engineering-backlog.md`), symbols ✓ (`GpxUploadForm.clean_file`, all grep targets verified against the live file), brief↔plan ✓. No `docs/reference/contract-surfaces.md` in this repo — surface check skipped.

## Findings

### F1 — §8's "Strategy (§1–§5) last reviewed" bullet goes stale

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Change 4 (§8 Freshness Ledger)
- **Detail**: §8 reads "Strategy (§1–§5) last reviewed: 2026-08-29" — a bullet covering §2 and §5, both edited by this plan today. §8's own refresh trigger list names "the project's tech stack changes" as a reason to refresh, which is exactly what's happening. The plan's Change 4 added a new scoped e2e ledger line but never revisited this bullet, and it wasn't part of the earlier Q&A (which only covered "Stack versions last verified").
- **Fix**: Bump "Strategy (§1–§5) last reviewed" to today's date as part of Change 4 — justified because Phase 1's manual verification already has the implementer read the whole document end-to-end for coherence, which is what this bullet is meant to record.
- **Decision**: FIXED — Change 4's Intent/Contract in plan.md now includes bumping this bullet to today, with rationale for why the other two ledger bullets stay untouched.

### F2 — Non-discriminating automated check for the new ledger line

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1, Automated Verification item 1.3
- **Detail**: `grep -q "e2e" context/foundation/test-plan.md` already returns true on the current, unedited file (4 pre-existing matches in the stale §4/§5 rows) — it cannot fail even if Change 4 is skipped entirely, so it proves nothing about whether the new ledger line landed. Same shape as the "assertion that doesn't back its own claim" pattern `lessons.md` #1 and this project's own suite-credibility gate exist to catch.
- **Fix**: Scope the check to §8 specifically so it can only pass if Change 4 actually landed.
- **Decision**: FIXED — item 1.3 now reads `sed -n '/^## 8\. Freshness Ledger/,/^## /p' context/foundation/test-plan.md | grep -q "e2e"`.

### F3 — A "visually confirm" step is filed under Automated Verification

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; renumbering touches Progress too
- **Dimension**: Plan Completeness
- **Location**: Phase 1, Automated Verification item 1.5 / Progress 1.5
- **Detail**: Item 1.5 ("File remains valid Markdown with no broken tables... visually confirm...") is a human action sitting under the Automated Verification heading, which should only contain machine-runnable commands. An implementer following the plan mechanically would either mis-check it off as automated or stall looking for a command that doesn't exist.
- **Fix**: Move the item to Manual Verification; Automated shrinks to 1.1–1.4, Manual grows to four items (1.5–1.8).
- **Decision**: FIXED — item moved to Manual Verification in the Phase 1 block and renumbered in `## Progress` (Automated 1.1–1.4, Manual 1.5–1.8).
