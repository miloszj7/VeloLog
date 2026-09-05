# Refresh test-plan.md for the Playwright e2e layer — Implementation Plan

## Overview

`context/foundation/test-plan.md` was last reviewed 2026-08-29, when no
Playwright MCP session was available and no rollout phase proposed e2e. Commit
`1a2b5ff` (2026-09-05) landed a real, working, isolated Playwright layer under
`tests/e2e/`. This plan refreshes the four places test-plan.md makes claims
that are now stale: §4 Stack, §5 Quality Gates, §2 Risk Response Guidance, and
§8 Freshness Ledger — bringing the document back in line with what the
codebase actually has, without promoting e2e to a required CI gate or adding a
new top-N risk.

## Current State Analysis

- §4's e2e row reads `| e2e | none yet | — | Not proposed by any rollout
  phase... |` and its "Stack grounding tools" note states "Playwright MCP —
  not available in current session." Both are now false: `tests/e2e/` exists,
  works, and was verified red-then-green on a deliberate break
  (`research.md`, "e2e infra shape").
- §5's e2e row reads `| e2e on critical flows | — | not planned | see §4... |`.
  `.github/workflows/deploy.yml` has zero e2e/playwright references, so "not
  a required gate" is true today as fact, not merely as future intent —
  confirmed in `research.md` ("CI wiring — confirmed absent").
- §2's Risk Response Guidance table has no reference to e2e for Risk #1 or
  Risk #6. Their "Likely cheapest layer" cells currently read plain
  `integration` (Risk #1) and `integration asserting the empty-state marker`
  (Risk #6) — both correct claims about the *primary* layer that this plan
  must not disturb.
- §8's Freshness Ledger has three bullets, all dated 2026-08-29, none scoped
  to e2e specifically.
- `tests/e2e/gpx-upload.spec.ts` — the concrete test that would anchor the
  Risk #1/#6 e2e claim by name — is **currently untracked** (git status,
  confirmed at planning time). Per the planning decision below, this plan
  does not commit it; test-plan.md cites the committed `seed.spec.ts` as its
  anchor and describes the GPX-upload e2e pattern generically.

### Key Discoveries:

- `tests/e2e/playwright.config.ts:18-47` — isolated npm project, `testDir:
  '.'`, two-project `setup`→`e2e` dependency, `webServer` boots `uv run
  python manage.py runserver 8000` against `/healthz/`, `reuseExistingServer:
  !process.env.CI`.
- `tests/e2e/auth.setup.ts:16-30` — `storageState`-based auth; logs in
  through the real UI once, persists `playwright/.auth/user.json`. Throws
  immediately if `E2E_USERNAME`/`E2E_PASSWORD` are unset, and login itself
  fails if no such Django user exists — **no fixture provisions this
  account**, it must already exist in whatever DB the run targets
  (`tests/e2e/.env.example`: "Any account works — no admin/staff rights
  needed").
- `.github/workflows/deploy.yml` — no e2e/playwright reference anywhere in
  the `gates` job.
- `context/foundation/engineering-backlog.md:69-73` — the root
  `package.json` (Railway IaC) is already documented as a separate,
  deliberately-scoped Node footprint; no reconciliation needed with
  `tests/e2e/package.json`.

## Desired End State

`context/foundation/test-plan.md` accurately describes the e2e layer as it
exists today: a real, narrow-slice Playwright suite, not a required gate, with
its stack facts, quality-gate status, and Risk #1/#6 protection role all
stated correctly and traceable to evidence. A reader encountering the plan
after this change should not be able to find any claim in these four sections
that the codebase contradicts.

**Verification**: read the four edited sections side-by-side with
`git show HEAD:tests/e2e/playwright.config.ts`,
`git show HEAD:tests/e2e/auth.setup.ts`, and `.github/workflows/deploy.yml` —
every stack/gate claim should trace to one of those three sources.

## What We're NOT Doing

- Not promoting e2e to a required CI gate — no edit to
  `.github/workflows/deploy.yml` or `lefthook.yml`.
- Not adding a new top-N risk row to §2's Risk Map — the e2e note is a
  supplementary layer on existing Risk #1 and Risk #6, stated in prose below
  the Risk Response Guidance table, never a new table row.
- Not proposing map/tile visual e2e testing — §7 already excludes this and
  stays untouched.
- Not committing `tests/e2e/gpx-upload.spec.ts` — that stays a separate,
  later change; this plan touches only `context/foundation/test-plan.md` and
  `context/changes/test-plan-refresh-2026-09-05/change.md`.
- Not opening a new §3 rollout phase — this is a stack/gate/risk-guidance
  refresh of already-frozen strategy sections, not a new phased-rollout row.
- Not re-verifying or re-dating stack facts other than the e2e one — §8 gets
  one new, narrowly-scoped line; the existing "Strategy last reviewed" and
  "Stack versions last verified" bullets stay at 2026-08-29 since nothing
  else in the stack table was re-checked this session.

## Implementation Approach

Single pass, four section edits in one file, in document order (§2 → §4 →
§5 → §8) so each edit can be diffed independently even though they land in
one commit. Every new sentence traces to a specific fact already surfaced in
`research.md` — no new codebase research is needed to write the prose.

## Phase 1: Refresh test-plan.md

### Overview

Update all four stale sections of `context/foundation/test-plan.md` to
reflect the landed Playwright e2e layer, then stamp `change.md` as planned
(already done during planning) and leave the change ready for `/10x-implement`
to execute and archive.

### Changes Required:

#### 1. §2 Risk Response Guidance — supplementary e2e note

**File**: `context/foundation/test-plan.md`

**Intent**: Add one short paragraph immediately after the Risk Response
Guidance table (before the `## 3. Phased Rollout` heading) stating that a
narrow-slice e2e layer now exists as an *additional* protection layer on Risk
#1 (file lifecycle) and Risk #6 (rendered-page degradation), covering the one
thing neither the Django test client nor an integration test reaches: a real
browser multipart file-upload widget round-tripping through
`GpxUploadForm.clean_file` into rendered stage/stats DOM, surviving a hard
reload. Explicitly state this does not change either risk's "Likely cheapest
layer" verdict (`integration` stays the primary/cheapest layer for both) —
e2e is supplementary, not a replacement.

**Contract**: A new paragraph, not a new table row or column. Must not alter
any existing table cell (per the "What We're NOT Doing" constraint — no
inline edit to the "Likely cheapest layer" column). Must name the specific
seed.spec.ts pattern as evidence (committed, verified red-then-green on a
deliberate break) without naming `gpx-upload.spec.ts` by path, since that
file is uncommitted.

#### 2. §4 Stack — e2e row and grounding-tools note

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the `| e2e | none yet | — | Not proposed by any rollout
phase... |` row with a row describing the real stack: Playwright
`^1.55.1`, `testDir: tests/e2e/`, isolated `package.json` (separate from the
root Railway-IaC one), `storageState`-based auth via `auth.setup.ts`,
`webServer` boots the Django dev server against `/healthz/`. Add a `checked:`
date (today) to this row, following the table's existing convention for
AI-native/verified entries. Include the manual-provisioning caveat (a real
pre-existing Django user + DB is required; no fixture creates the account)
briefly in the Notes column. Also update the "Stack grounding tools" bullet
list's Playwright MCP line, which currently states "not available in current
session" as the reason no e2e phase was proposed — correct it to reflect that
a working e2e layer now exists outside of Playwright MCP (the seed test was
authored and verified directly, not through the MCP browser-automation tool),
and that this refresh is not itself a new rollout phase.

**Contract**: One table row rewritten in the §4 Stack table; one bullet
updated under "Stack grounding tools (current session)". Row must state tool,
version, testDir, package isolation, auth mechanism, webServer target, and
the manual-provisioning caveat — matching the level of detail change.md
specifies.

#### 3. §5 Quality Gates — e2e row

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the `| e2e on critical flows | — | not planned | see
§4... |` row with one stating the gate is "narrow slice only" — not a
required CI gate — and name the reason: cost × signal still favors
integration for ownership/lifecycle/rejection (the three areas §3's Phases
1–3 already cover), consistent with §1's own strategy principle #1. State
plainly, as a fact confirmed against the workflow file, that
`.github/workflows/deploy.yml`'s `gates` job has no e2e step.

**Contract**: One table row rewritten in the §5 Quality Gates table. Must not
introduce a "Required after §3 Phase `<N>`" framing — there is no phase this
gate becomes required after, since it isn't planned to become required.

#### 4. §8 Freshness Ledger — scoped e2e verification line

**File**: `context/foundation/test-plan.md`

**Intent**: Add one new bullet recording that the e2e stack fact was verified
today, scoped narrowly so it doesn't imply the whole stack table was
re-reviewed. Also bump the existing `Strategy (§1–§5) last reviewed` bullet
to today — §2 and §5, both inside that range, are edited by this same phase,
and Phase 1's manual verification (1.8, renumbered from plan-review F3) already
has the implementer read the whole document end-to-end for coherence, which is
what this bullet is meant to record. Leave `Stack versions last verified` and
`AI-native tool references last verified`, both dated 2026-08-29, untouched —
neither claim is falsified by this refresh (the e2e stack row gets its own new
scoped line instead of piggybacking on the blanket stack-versions claim).

**Contract**: One new bullet under `## 8. Freshness Ledger`, dated today,
naming specifically the e2e stack facts (Playwright layer existence, version,
CI-gate status) as what was verified — not a blanket restatement of the
existing bullets. Plus: the existing `Strategy (§1–§5) last reviewed:
2026-08-29` bullet's date changed to today.

#### 5. Header freshness line and header "Last updated" date

**File**: `context/foundation/test-plan.md`

**Intent**: The document header (line 9) currently reads `> Last updated:
2026-08-31`. Bump it to today's date, since this refresh is itself an update
to the frozen strategy sections (§1–§5), consistent with the header's own
purpose of telling a reader when the frozen sections were last touched.

**Contract**: One date string changed on the header line.

### Success Criteria:

#### Automated Verification:

- `grep -q "none yet" context/foundation/test-plan.md` returns no match (the
  stale e2e stack claim is gone): `! grep -q "none yet" context/foundation/test-plan.md`
- `grep -q "not planned" context/foundation/test-plan.md` no longer matches
  the e2e gate row specifically — verify by inspecting the §5 e2e row text
  directly (grep for "narrow slice"): `grep -q "narrow slice" context/foundation/test-plan.md`
- New Freshness Ledger line present, scoped to §8 so the check can only pass
  if Change 4 landed: `sed -n '/^## 8\. Freshness Ledger/,/^## /p' context/foundation/test-plan.md | grep -q "e2e"`
- Header date bumped: `grep -q "Last updated: 2026-09-05" context/foundation/test-plan.md`

#### Manual Verification:

- Read §2's new paragraph, §4's rewritten row, §5's rewritten row, and §8's
  new bullet end-to-end and confirm every claim traces to
  `tests/e2e/playwright.config.ts`, `tests/e2e/auth.setup.ts`,
  `tests/e2e/seed.spec.ts`, or `.github/workflows/deploy.yml` as read during
  planning.
- Confirm no new top-N risk row was added to §2's Risk Map and no existing
  table cell (Risk #1 or #6's "Likely cheapest layer") was altered.
- Confirm §7 ("What We Deliberately Don't Test") was not touched — map/tile
  visual testing exclusion stays exactly as-is.
- File remains valid Markdown with no broken tables: visually confirm every
  `|---|` row count matches its header row count in §2, §4, §5 (no automated
  linter is wired for this repo's docs — manual table-shape check substitutes).

**Implementation Note**: After completing this phase and all automated
verification passes, pause here for manual confirmation from the human that
the manual read-through was successful before archiving the change.

---

## Testing Strategy

### Unit Tests:

Not applicable — this change edits a Markdown planning document, not code.

### Integration Tests:

Not applicable.

### Manual Testing Steps:

1. Open `context/foundation/test-plan.md` and read §2, §4, §5, §8 top to
   bottom.
2. Cross-check each new/changed sentence against `tests/e2e/*` and
   `.github/workflows/deploy.yml` as listed in "Key Discoveries" above.
3. Confirm the document still reads coherently as a whole — no orphaned
   references to the old "none yet" / "not planned" / "Playwright MCP not
   available" framing anywhere else in the file (§1, §3, §6, §7 are
   otherwise untouched and should still make sense next to the refreshed
   §2/§4/§5/§8).

## Performance Considerations

None — documentation-only change.

## Migration Notes

None — no schema, data, or code changes.

## References

- Related research: `context/changes/test-plan-refresh-2026-09-05/research.md`
- e2e infra: `tests/e2e/playwright.config.ts`, `tests/e2e/auth.setup.ts`,
  `tests/e2e/seed.spec.ts`
- CI gate baseline: `.github/workflows/deploy.yml`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a
> step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Refresh test-plan.md

#### Automated

- [x] 1.1 `! grep -q "none yet" context/foundation/test-plan.md`
- [x] 1.2 `grep -q "narrow slice" context/foundation/test-plan.md`
- [x] 1.3 New Freshness Ledger e2e line present, scoped to §8
- [x] 1.4 Header date bumped to 2026-09-05

#### Manual

- [x] 1.5 Every new/changed claim traces to `tests/e2e/*` or
      `.github/workflows/deploy.yml`
- [x] 1.6 No new top-N risk row added; Risk #1/#6 table cells unaltered
- [x] 1.7 §7 untouched; document reads coherently end to end
- [x] 1.8 No broken Markdown tables in §2, §4, §5
