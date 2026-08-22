---
project: VeloLog
migrated: 2026-08-22
source: context/foundation/roadmap.md (v1)
workspace: MiloszJ (https://linear.app/miloszj)
team: 10xdevs
---

# Linear Issues mirror

Records the format, labels, and decisions used to mirror roadmap items from
`context/foundation/roadmap.md` into Linear, alongside the existing
`context/foundation/github-issues-migration.md` migration to GitHub Issues on
`miloszj7/VeloLog`. One-time, one-way mirror: `roadmap.md` → Linear issues. There is
no sync back — changing an issue's status or labels in Linear does **not** update
`roadmap.md`'s `Status` field, and re-running this on an unchanged roadmap would
create duplicates (no Change-ID-based idempotency check exists).

## Scope

Same scope as the GitHub migration: only rows from `## At a glance` / `## Backlog
Handoff` (`S-NN` roadmap items) were mirrored. `## Parked` and `## Open Roadmap
Questions` were **not** mirrored. At mirror time the roadmap had 5 slices and 0
foundations.

## Team and project

Created in the **`10xdevs`** team (chosen over the personal `MiloszJ` team so VeloLog
tracks alongside other 10xdevs coursework). A new Linear **project**, `VeloLog`, was
created to group the issues (mirrors having a dedicated GitHub repo) — no Linear
project existed beforehand.

## Labels

Same name/color scheme as the GitHub migration, created on the `10xdevs` team:

| Label | Color | Meaning |
|---|---|---|
| `roadmap` | `#6e7681` | Generic marker: this issue originated from `roadmap.md` |
| `type:slice` | `#0e8a16` | Corresponds to a roadmap `S-NN` — vertical slice |
| `type:foundation` | `#5319e7` | Corresponds to a roadmap `F-NN` — foundation (none existed at mirror time; label created for future use) |
| `status:proposed` | `#ededed` | Mirrors roadmap `Status: proposed` |
| `status:ready` | `#c2e0c6` | Mirrors roadmap `Status: ready` |
| `status:planning` | `#bfd4f2` | Mirrors roadmap `Status: planning` |
| `status:in-progress` | `#fbca04` | Mirrors roadmap `Status: in-progress` |
| `status:blocked` | `#e11d21` | Mirrors roadmap `Status: blocked` |
| `status:done` | `#0e8a16` | Mirrors roadmap `Status: done` |

Linear's default team labels (`Feature`, `Improvement`, `Bug`) were left untouched and
are not used by this mirror.

## Status mapping

Linear's native workflow only has 5 states (Backlog / Todo / In Progress / Done /
Canceled), one short of the roadmap's 6-state `Status` field. Status is therefore
mirrored two ways — the native issue status (coarse) plus a `status:*` label (exact),
the same dual-track approach the GitHub migration used with GitHub's open/closed state
plus `status:*` labels:

| Roadmap `Status` | Linear native status | `status:*` label |
|---|---|---|
| proposed | Backlog | `status:proposed` |
| ready | Todo | `status:ready` |
| planning | Todo | `status:planning` |
| in-progress | In Progress | `status:in-progress` |
| blocked | Todo | `status:blocked` |
| done | Done | `status:done` |

## Milestone

A single milestone, **"VeloLog v1"**, target date `2026-09-10` (the PRD/roadmap hard
deadline), was created inside the `VeloLog` project and assigned to all 5 issues. No
per-slice milestones — mirrors the GitHub migration's single-milestone approach.

## Issue format

**Title:** identical to the roadmap slice heading, e.g. `S-01: User can register, log
in, and log out` — same convention as the GitHub migration.

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
<list of Linear issue refs, or `_None_`>

### Parallel with
<list of Linear issue refs, or `_None_`>

### Blockers
<from roadmap.md, or `_None_`>

### Unknowns
<from roadmap.md, or `_None_`>

### Risk
<Risk from roadmap.md>

---
Source: `context/foundation/roadmap.md` · Mirrors GitHub issue #<N> · Roadmap status at mirror: `<status>`
```

**Labels per issue:** `roadmap`, `type:slice` (or `type:foundation`), plus one
`status:<status>` matching the roadmap's `Status` field at mirror time.

## Dependency linking

Issues were created in roadmap dependency order — **S-01 → S-02 → S-03 → S-04 → S-05**
— so every `Prerequisites`/`Parallel with` reference could link a real Linear issue at
creation time. The one forward reference (S-03's `Parallel with: S-04`, where S-04
didn't exist yet) was backfilled via a `patch` edit once S-04 was created — same
approach the GitHub migration used with `gh issue edit`.

Prerequisite relationships were also encoded as native Linear `blockedBy` relations
(not just text in the description), which GitHub Issues has no equivalent for:
S-02 blocked by S-01; S-03 and S-04 blocked by S-02; S-05 blocked by S-03.

## Result

| Roadmap ID | Change ID | Linear Issue |
|---|---|---|
| S-01 | `user-registration-login` | [10X-1](https://linear.app/miloszj/issue/10X-1/s-01-user-can-register-log-in-and-log-out) |
| S-02 | `create-and-list-trips` | [10X-2](https://linear.app/miloszj/issue/10X-2/s-02-user-can-create-a-trip-and-see-it-in-their-trip-list) |
| S-03 | `upload-gpx-and-view-map` | [10X-3](https://linear.app/miloszj/issue/10X-3/s-03-user-can-upload-a-gpx-file-and-see-the-route-as-a-static-map) |
| S-04 | `edit-and-delete-trip` | [10X-4](https://linear.app/miloszj/issue/10X-4/s-04-user-can-edit-and-delete-a-trip) |
| S-05 | `trip-distance-duration-stats` | [10X-5](https://linear.app/miloszj/issue/10X-5/s-05-user-can-view-basic-trip-stats) |

`context/foundation/roadmap.md`'s `## Backlog Handoff` table was updated with a
`Linear Issue` column pointing back to these issues.
