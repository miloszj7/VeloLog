# Frame Brief: GPX upload orphan file (roadmap E-11)

> Framing step before /10x-plan. This document captures what is *actually*
> at issue, separated from what was initially assumed.

## Reported Observation

Verbatim from `context/foundation/roadmap.md:163` (E-11), which itself came from
`context/archive/2026-08-26-edit-and-delete-trip/reviews/impl-review.md:242-270` (F10),
accepted-not-fixed at commit `6b10cee`:

> A GPX upload whose transaction rolls back leaves its file in storage with no row
> pointing at it (`gpx/views.py:100-113`) — `super().form_valid(form)` writes the file
> *inside* `transaction.atomic()`, and storage writes do not participate in the
> transaction. The `post_delete` receiver can never reach such a file: it fires on
> deletes, not on failed inserts, so this is the one gap in the "lifecycle owned
> end-to-end" claim in `AGENTS.md`.

## Initial Framing (preserved)

- **User's stated cause or approach**: the file write sits *inside* `transaction.atomic()`,
  and that placement is what produces the orphan.
- **User's proposed direction**: "Move the file write outside the atomic block, or register
  a compensating rollback hook that discards the newly written file."
- **Pre-dispatch narrowing**: E-11 has **never been observed** — it is code-reading only,
  from the F10 review; scope is the **whole orphan class**, not just the rollback window;
  and the consequence that matters is **unreclaimable storage growing on the Railway volume**
  (not the `AGENTS.md` claim, not a user-visible symptom).

## Dimension Map

A file can end up in storage with no row pointing at it at any of these dimensions:

1. **The atomic rollback window** — the write inside `atomic()` at `gpx/views.py:117`,
   something raises before COMMIT. ← initial framing
2. **Row-preserving replacement** — a path that overwrites `GpxTrack.file` while keeping
   the row, so `post_delete` never fires.
3. **Non-exception loss** — no rollback needed: worker timeout, SIGKILL, redeploy landing
   between the storage write and the COMMIT.
4. **No detection or reclamation** — nothing can find or remove an orphan, so every one
   that exists stays on the volume permanently and invisibly.

## Hypothesis Investigation

| Hypothesis | Evidence | Verdict |
| --- | --- | --- |
| **1. The `atomic()` placement is the cause** (initial framing) | The write is *welded* to the INSERT: `FileField.pre_save` (`django/db/models/fields/files.py:325-339`) calls `FieldFile.save`, whose `storage.save()` at `files.py:98` runs from inside the same `Model.save()` field loop that then issues the INSERT (`base.py:1154-1170`). Not separable by any parameter. The orphan reproduces under plain autocommit `objects.create()` with **no transaction anywhere**. Removing `atomic()` measures the window from ~0.20 s to ~0.11 s — it does not close. | **STRONG — but as a refutation.** The stated cause is false. |
| **1a. "Move the write outside the atomic block" fixes it** | Bytes on disk at T0 outside any transaction, INSERT rolls back at T1 (`transaction.py:271-300`), nothing deletes the file — identical orphan. Removes only the cascade-delete segment, ~30% of the window. | **NONE.** Does not work. |
| **1b. "Register a compensating rollback hook"** | No `on_rollback` primitive exists in Django 6.0.5 — zero hits for `on_rollback\|run_on_rollback\|rollback_hook` across the installed package. `rollback()` *wipes* `run_on_commit` wholesale (`base/base.py:341`), so nothing can ride on `on_commit`. Expressible only as a hand-rolled `try/except` **around** the `with` — because `connection.commit()` can raise in `Atomic.__exit__` (`transaction.py:249-259`) where no in-block handler sees it. | **WEAK.** Real but hand-rolled, and covers only the exception path. |
| **2. Row-preserving replacement** | `gpx/admin.py:27` excludes only `points`, so `file` is an editable upload field on the change form. `FileField.save_form_data` (`files.py:360-370`) discards the old `FieldFile` without consulting it; `pre_save` writes the new file with **no reference to the previous column value**; the row is `UPDATE`d, so `post_delete` (`gpx/signals.py:66`) never fires. `gpx_upload_path` (`gpx/models.py:17`) returns `secrets.token_hex(16)`, so the new key can **never** overwrite the old one — the strand is deterministic, not incidental. Zero hits for `storage.delete` across `django/contrib/admin/`, `django/forms/models.py`, `django/db/models/deletion.py`. No admin change-form test exists in the suite. | **STRONG.** Live, deterministic, fires on ordinary success. |
| **3. Non-exception loss** | `railway.json:4` configures nothing — gunicorn defaults apply: `workers=1`, `threads=1`, sync, `timeout=30`, `graceful_timeout=30`. `Worker.handle_abort` → `sys.exit(1)` (`workers/base.py:195-198`) drives `SystemExit` through `atomic.__exit__`, producing the orphan through the identical rollback with **no application exception at all**; SIGKILL skips the rollback and yields the same on-disk state. Structurally irreducible by ordering. **But the frequency claim fails**: measured parse at the 100k-point cap is ~2.0 s and *all* of it precedes the write (`gpx/forms.py:60`, in `clean_file`), so a 30 s SIGABRT lands upstream of the window; and SIGTERM drain (`workers/sync.py:60,88`) gives a ~2 s request 30 s of headroom. | **STRONG on structure, refuted on frequency.** |
| **4. No detection or reclamation** | Zero hits for `listdir\|iterdir\|glob(\|walk(\|scandir` across `accounts/ trips/ gpx/ velo_log/` — every filesystem touch is keyed by an exact name from the database, so detection is **structurally unreachable**, not merely unwritten. One management command exists (`backfill_gpx_stats`, read-only w.r.t. storage). Nothing measures disk usage; `/healthz/` (`velo_log/urls.py:155-200`) probes media *reachability*, never size. `gpx/signals.py:62` logs `storage_key` in `extra=`, which the formatter at `velo_log/settings.py:233` **drops** (known and accepted, `context/archive/2026-08-26-logging-config/plan.md:86-87`) — you learn a delete failed, never which file. | **STRONG.** Absent, totally. |

### Two sources the dimension map did not anticipate

Surfaced by the unprimed cross-check (Step 5), which was told only the observation:

- **Ops restore, nested upload** — `DEPLOY.md:151` records this *already firing once*:
  `files upload` "Created `/data/media/<backup-name>/` and left the live files untouched.
  **Reported success.**" A full duplicate of the entire corpus. `DEPLOY.md:166-175`:
  `railway service files delete` is refused for non-humans, so only a person can reclaim it.
- **Ops restore, point-in-time skew** — restoring the DB to T-1mo while `/data/media` keeps
  every file uploaded since. Those `token_hex` names are in neither the restored DB nor the
  backup archive, and the documented media upload (`DEPLOY.md:130`) prunes nothing. Produced
  by *correct* execution of the documented procedure.
- Minor, same shape: `gpx/signals.py` deletes files but never their parent directories.
  **Four empty `media/gpx/<owner>/<trip>/` dirs exist locally right now** (`1/6`, `1/7`,
  `1/8`, `8/12`).

## Narrowing Signals

Decisive observations that narrowed the hypothesis space:

- **The owner uses the admin change form as a repair path** (Step 4). This promotes
  dimension 2 from theoretical to live: every such repair to date has stranded the previous
  file, silently, with a 302 and a green audit log.
- **The stated consequence is volume bytes, not correctness** (Step 1.5). That makes
  *ranking by bytes/year* the deciding lens, and E-11 ranks near the bottom of it.
- **E-11 has never been observed** (Step 1.5) — and could not have been: nothing in the
  repo can see an orphan.
- **The restore-drill stray tree has never been checked** (Step 4) — the project's largest
  known orphan event is of unknown current status on the production volume.

### Expected bytes per year, all sources ranked

Assumptions: ~60 uploads/yr, mean GPX ~0.8 MB (measured from this repo's own `media/`),
`MAX_GPX_FILE_MEGABYTES = 10` (`gpx/constants.py`).

| Rank | Source | Trigger class | Expected/yr |
| --- | --- | --- | --- |
| 1 | Ops restore, nested upload | Procedure error — **already fired once** | ~14 MB |
| 2 | Ops restore, PIT skew | **Ordinary correct execution** | ~2 MB |
| 3 | Admin change-form replacement | **Ordinary success** — confirmed in use | ~1.6 MB |
| 4 | Empty `<owner>/<trip>/` directories | **Ordinary success** (every delete) | ~0.25 MB |
| 5 | `post_delete` cleanup swallowed (`signals.py:59`) | Failure | ~0.2 MB |
| **6** | **E-11, rolled-back upload** | **Crash only** | **~0.16 MB** |

E-11 is the only member of the class that requires a crash, and the only one with a roadmap
row, a change folder, an `AGENTS.md` caveat and a named review finding.

## Cross-System Convention

This project has met this exact problem shape **five times** and resolved it four ways, all
by *prevention at the write site*: the `/healthz/` probe orphan (F1, bounded to one fixed
key plus a reclaiming delete at `velo_log/urls.py:140` — the one reclamation precedent in
the codebase, never generalized); the concurrent-upload race (F2, `7d4a523`); the
delete-path lifecycle (`d746f0f`, refined by `c517b8b` and `9548b67`); and E-11 itself,
accepted rather than fixed (`6b10cee`).

**No occurrence has ever proposed reconciliation.** The convention is prevention, and the
convention is what left the class uncovered — prevention only ever closes the path it was
aimed at. Note also the instrumentation asymmetry: the *inverse* fault, a row whose file is
gone, is caught, logged with context and answered 404 (`gpx/views.py:140-153`, `d4df931`),
and documented at `DEPLOY.md:110-113`. The orphan direction has no log line, no doc line
and no test.

## Reframed Problem Statement

> **The actual problem to plan around is**: VeloLog cannot detect or reclaim an unreferenced
> file in `MEDIA_ROOT` — and the orphan population is dominated by paths that *succeed*,
> not by the crash window E-11 names.

E-11's observation is true and its stated cause is false. The write is inside `atomic()`,
but that is not why the orphan happens: `FileField.pre_save` welds the storage write to the
INSERT two frames below anything the view can see, and the orphan reproduces with no
transaction at all. Consequently its first proposed fix does not work, and its second closes
only the exception path while a deterministic orphan — the admin change form the owner
actually uses — sits outside the transaction entirely, in a path `AGENTS.md` explicitly
claims is covered. Against the stated consequence of volume bytes, closing E-11 as written
is close to the lowest-yield action available: roughly 100× smaller than the ops path
`DEPLOY.md` already records as having misfired in production.

## Confidence

**HIGH.**

Four parallel investigations plus an unprimed cross-check that was given only the
observation. All five converged; the cross-check independently reproduced the ranking and
added the two ops sources and the empty-directory case that the dimension map had missed.
Every load-bearing claim is anchored in installed Django source, project source, measured
timings, or the project's own written history.

One deliberate gap, worth naming rather than hiding: the **Railway volume's capacity is
documented nowhere in the repo** (`infrastructure.md:60` records the volume's IOPS, never
its size). The bytes/year ranking is therefore sound in *relative* terms — which it needs to
be, to rank the sources — but the absolute question "how long until this matters" cannot be
answered from the repo. E-07's `$5` spend alert, the only channel through which metered
volume storage could ever surface, has been flagged un-reverified since 2026-08-21
(`DEPLOY.md:193-197`; the roadmap's citation of `DEPLOY.md:43` is stale).

## Verification (2026-08-28) — MEASURED, both environments

The ranking above is a projection. It has now been checked against reality, and the result
is **zero orphans anywhere**.

**Production volume: clean.** Full enumeration via `railway service files list --json`
(requires `MSYS_NO_PATHCONV=1` under Git Bash — the trap `AGENTS.md` names; without it the
CLI mangles `/data` into `/C:/Program Files/Git/data` and fails):

| Path | Contents |
| --- | --- |
| `/data` | `db.sqlite3` (233,472 B), `lost+found/` (empty), `media/` |
| `/data/media` | `gpx/`, `healthz/` (empty — the probe deletes its own file, as designed) |
| `/data/media/gpx/1/{1,2,3,4}` | exactly **one** `.gpx` each: 405 / 126,484 / 317 / 1,090,724 B |

Set-differenced against `SELECT file FROM gpx_gpxtrack` in a downloaded copy of the
production database (since deleted): **4 rows ↔ 4 files, exact match in both directions.
No orphan, no missing file.** Scale for context: 4 trips, 3 users.

Three projected sources are therefore confirmed **not to have fired in production**:

- **Rank 1, the nested restore tree** — no timestamp-named directory exists at `/data` or
  `/data/media`. Either it never landed or it was reclaimed after the drill.
- **Rank 3, admin change-form replacement** — every trip directory holds exactly one file.
  A stranded predecessor would show as a second `.gpx` in the same directory. None does.
- **Rank 6, E-11 itself** — same signature, also absent.

**The 43 MB is filesystem overhead, not data.** `railway status` reports
`velolog-volume · /data · 43 MB / 500 MB`, but actual content totals **1.38 MiB**
(1,217,930 B media + 233,472 B database). The remaining ~41 MB is ext4 journal, inode
tables and reserved blocks on a 500 MB volume. This also supplies the capacity figure the
brief records as undocumented anywhere in the repo — and it is **500 MB, an order of
magnitude smaller than the 5 GB assumed while ranking**.

**Local working copy: clean.** 3 files ↔ 3 rows, exact match. The **four empty
`media/gpx/<owner>/<trip>/` directories are confirmed present** (`1/6`, `1/7`, `1/8`,
`8/12`), so that member of the class is real — locally only; production has none.

### What the measurement changes, and what it does not

**Changes:** there is no backlog to clean up. Every prevention-shaped option now has an
empty starting set, and the storage-growth consequence is, at current scale, not
approaching anything: 1.38 MiB of 500 MB, against a top projected source of ~14 MB/yr that
has demonstrably not fired.

**Does not change:** the reframe itself. E-11's stated cause is still false, its first
proposed fix still does not work, and the admin change form still strands a file whenever
it is used to replace one — the owner confirms using it as a repair path, so this is a
question of *when*, not *whether*. Above all: **answering "are there orphans?" required a
hand-rolled multi-step CLI walk plus a production database download.** That the question
could not be answered from inside the product is the reframe's central claim, demonstrated
rather than argued.

## What Changes for /10x-plan

The plan should be about **the orphan population, not the rollback window** — the owner's
confirmed scope. It inherits a measured starting position: **the population is currently
empty in both environments**, the volume is 500 MB holding 1.38 MiB, and no projected source
has yet fired in production. That is an argument about *urgency and sizing*, not about
correctness — and it is the plan's to weigh, including the option of doing less than E-11
implies. Two constraints, both evidence, not design:

1. E-11's first proposed fix is refuted and should not be planned; its second is expressible
   only as a hand-rolled `try/except` around the `with`, and covers the exception path only.
   Whatever is chosen, the process-death member of the class is irreducible by ordering.
2. Any prevention-shaped plan leaves every already-existing orphan on the volume, since
   nothing can currently see one. The ranking above is what the plan should prioritize
   against; /10x-plan owns the choice of instrument.

Three loose ends this brief opened, for the plan to place or defer explicitly:

- `AGENTS.md`'s receiver-coverage list names `delete_selected` but omits the admin **change
  form**, and its "lifecycle owned end-to-end" claim is false for a live path (lesson 5:
  a stale `AGENTS.md` claim actively misdirects the next agent).
- The 2026-08-26 restore-drill stray tree has never been checked on the production volume.
- E-11's own text needs correcting regardless of what is built: the cause is wrong and the
  line cite has drifted (`gpx/views.py:100-113` → the block is `104-119`, write at `117`).

## References

- Source: `gpx/views.py:104-119`, `gpx/signals.py:66-99`, `gpx/admin.py:26-27`,
  `gpx/models.py:8-17,29`, `gpx/forms.py:52-82`, `gpx/constants.py:5-8,22`,
  `velo_log/settings.py:98-103,233,248`, `velo_log/urls.py:126-200`, `railway.json:4`
- Django 6.0.5 (installed): `db/models/fields/files.py:96-104,325-339,360-370`,
  `db/models/base.py:1154-1170`, `db/transaction.py:129-136,249-315`,
  `db/backends/base/base.py:341,727-750`, `db/models/deletion.py:458`
- Prior decisions: `context/archive/2026-08-26-edit-and-delete-trip/reviews/impl-review.md:242-270`
  (F10, origin of E-11), `context/archive/2026-08-23-upload-gpx-and-view-map/reviews/impl-review-phases-1-2.md:40-95`
  (F1), `.../impl-review-phase-4.md:98-114` (F2), `context/foundation/roadmap.md:163` (E-11),
  `:159` (E-07), `:157` (E-05)
- Runbook: `DEPLOY.md:123-175,193-197`
- Tests: `tests/gpx/test_gpx_signals.py:209-235` (mirror case, rolled-back *delete*),
  `tests/gpx/test_gpx_upload.py:311-344,348` — no test covers a rolled-back upload, and
  none covers the admin change form
