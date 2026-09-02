---
project: VeloLog
migrated: 2026-08-22
source: context/foundation/roadmap.md (v1)
repo: miloszj7/VeloLog
---

# GitHub Issues migration

Records the format, labels, and decisions used to migrate roadmap items from
`context/foundation/roadmap.md` into GitHub Issues on `miloszj7/VeloLog`. One-time,
one-way migration: `roadmap.md` → GitHub Issues. There is no sync back — closing an
issue or changing its labels does **not** update `roadmap.md`'s `Status` field, and
re-running this migration on an unchanged roadmap would create duplicates (no
Change-ID-based idempotency check exists).

**2026-08-31 update:** Linear mirror retired → `context/foundation/archive/linear-issues-migration-2026-08-31.md`.
GitHub Issues is now the single source of truth for roadmap tracking. Manual sync
adopted: when a GitHub issue with the `roadmap` label is closed, update `roadmap.md`'s
`Status` field by hand.

## Scope

Only rows from `## At a glance` / `## Backlog Handoff` (i.e. `F-NN` and `S-NN` roadmap
items — actual backlog points) were migrated. `## Parked` (explicitly deferred) and
`## Open Roadmap Questions` (questions, not tasks) were **not** migrated.

At migration time the roadmap had 5 slices and 0 foundations.

## Labels

| Label | Color | Meaning |
|---|---|---|
| `roadmap` | `#6e7681` | Generic marker: this issue originated from `roadmap.md` |
| `type:slice` | `#0e8a16` | Corresponds to a roadmap `S-NN` — vertical slice |
| `type:foundation` | `#5319e7` | Corresponds to a roadmap `F-NN` — foundation (none existed at migration time; label created for future use) |
| `type:eng-backlog` | `#8250df` | Corresponds to a roadmap `## Engineering Backlog` row — non-slice, non-foundation engineering debt (added 2026-08-23 for issue #7, `ci-quality-gates`; not part of the original migration scope) |
| `status:proposed` | `#ededed` | Mirrors roadmap `Status: proposed` |
| `status:ready` | `#c2e0c6` | Mirrors roadmap `Status: ready` |
| `status:planning` | `#bfd4f2` | Mirrors roadmap `Status: planning` |
| `status:in-progress` | `#fbca04` | Mirrors roadmap `Status: in-progress` |
| `status:blocked` | `#e11d21` | Mirrors roadmap `Status: blocked` |
| `status:done` | `#0e8a16` | Mirrors roadmap `Status: done` |

`type:*` and `status:*` labels mirror the roadmap's fields 1:1, so
`gh issue list --label status:ready` matches the roadmap's `Status: ready` rows.
GitHub's default labels (`bug`, `enhancement`, `documentation`, …) were left untouched
and are not used by this migration.

## Milestone

A single milestone, **"VeloLog v1"**, due `2026-09-10` (the PRD/roadmap hard deadline),
was created and assigned to all 5 issues. No per-slice milestones.

## Issue format

**Title:** identical to the roadmap slice heading, e.g. `S-01: User can register, log
in, and log out` — keeps grep/matching consistent in both directions.

**Body template:**

```markdown
**Roadmap ID:** S-NN
**Change ID:** `<change-id>`
**Type:** Slice | Foundation

### Outcome
<Outcome from roadmap.md>

### PRD refs
<PRD refs from roadmap.md>

### Prerequisites
<list of `- #<issue> (S-NN)`, or `_None_`>

### Parallel with
<list of `- #<issue> (S-NN)`, or `_None_`>

### Blockers
<from roadmap.md, or `_None_`>

### Unknowns
<from roadmap.md, or `_None_`>

### Risk
<Risk from roadmap.md>

---
Source: [`context/foundation/roadmap.md`](<github blob URL + anchor>) · Roadmap status at migration: `<status>`
```

**Labels per issue:** `roadmap`, `type:slice` (or `type:foundation`), plus one
`status:<status>` matching the roadmap's `Status` field at migration time.

## Dependency linking

Issues were created in roadmap dependency order — **S-01 → S-02 → S-03 → S-04 → S-05**
— so every `Prerequisites` reference could link a real issue number at creation time
(a prerequisite is always created earlier in this order). The one forward reference
(`S-03`'s `Parallel with: S-04`, where S-04 didn't exist yet) was backfilled via
`gh issue edit` once S-04 was created.

## Result

| Roadmap ID | Change ID | GitHub Issue |
|---|---|---|
| S-01 | `user-registration-login` | [#1](https://github.com/miloszj7/VeloLog/issues/1) |
| S-02 | `create-and-list-trips` | [#2](https://github.com/miloszj7/VeloLog/issues/2) |
| S-03 | `upload-gpx-and-view-map` | [#3](https://github.com/miloszj7/VeloLog/issues/3) |
| S-04 | `edit-and-delete-trip` | [#4](https://github.com/miloszj7/VeloLog/issues/4) |
| S-05 | `trip-distance-duration-stats` | [#5](https://github.com/miloszj7/VeloLog/issues/5) |

`context/foundation/roadmap.md`'s `## Backlog Handoff` table was updated with a
`GitHub Issue` column pointing back to these issues.
