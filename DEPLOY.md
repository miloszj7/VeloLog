# Deploy Runbook

## Known-good deployments

Update this table after every production deploy.

| Date | Deployment ID | Notes |
|---|---|---|
| 2026-08-21 | `fe1df79b-aa06-49b2-8965-15f16992cfe4` | First production deploy (Phase 5). `collectstatic` + `migrate` + gunicorn all succeeded; `/healthz/` returns 200 with a real DB write/read round-trip on the mounted Volume. |
| 2026-08-22 | `365f39af-95a3-403a-8f78-14fb4aa162c1` | Ships S-01 (`user-registration-login`) — register/log in/log out. Verified via `railway status` (service Online) and `/healthz/` returning `{"status": "ok"}`. |
| 2026-08-23 | `f2197620-9267-4a92-b9e2-40abbf84b9fa` | Ships S-02 (`create-and-list-trips`) — create/list trips. Verified via `railway status` (deployment status `SUCCESS`, instance `RUNNING`). |
| 2026-08-26 | `39c7fb0c-9db8-4a3f-bc5b-03318dcfaed1` | Ships S-03 phases 1–5 (`upload-gpx-and-view-map`, commit `b2fa74b`) — GPX upload, download, and the route map. First deploy carrying user files. `/healthz/` returns `{"status": "ok", "database": "ok", "media": "ok"}`; all ten collected static assets fetch 200 under their content-hashed names. Note this is the *redeploy* triggered by setting `MEDIA_ROOT` — the deploy of `b2fa74b` immediately before it booted with media misconfigured (see below). |
| 2026-08-26 | `9c1e188b` (same commit `b2fa74b`) | Redeploy closing the restore drill below. Uploaded GPX files survived it on the Volume — the persistence proof this slice was gated on. `/healthz/` 200 with database and media both `ok`. |
| 2026-09-04 | `55137c9f-e175-4e61-a1d1-3ee2ed73886b` | Manual dashboard redeploy recovering from the E-04 incident below — `.railway/railway.ts` merge (PR #48) had cleared the service's Custom Start Command, so the automatic `railway up` deploy right after merge ran Railpack's auto-detected fallback (`python manage.py migrate && gunicorn ... velo_log.wsgi:application` — no `collectstatic`, no `uv run`) and 500'd. Fixed by re-pasting the real start command into the dashboard and redeploying from there; `railway config pull` now confirms it matches the repo's `.railway/railway.ts`. |
| 2026-09-04 | `91190b01-1c4c-4149-8d3a-6b968b442255` | Automatic `railway up` deploy from PR #49 (the corrected `.railway/railway.ts`) — code-only from the deploy's perspective, since `railway up` doesn't read that file. First deploy confirming the dashboard start command survives a normal merge-triggered redeploy. `/healthz/` returns `{"status": "ok", "database": "ok", "media": "ok"}`. |

## MEDIA_ROOT — required, and easy to set wrongly from Git Bash

**Set `MEDIA_ROOT=/data/media` before the first upload in any new environment.** Unset, it
falls back to `BASE_DIR / "media"` (`velo_log/settings.py:168`) — inside the container, not
on the Volume — and every uploaded file is destroyed by the next redeploy, silently.

This was caught in production on 2026-08-26, by the Phase 1 `/healthz/` probe rather than by
a lost file: the variable had never been set, so the deploy that first shipped the upload
feature booted with `{"media": "error", "media_error": "inside_base_dir"}` and a 500 on
`/healthz/`. No files were lost, because uploads had been reachable for only a few minutes.
`.railway/railway.ts` sets no `healthcheck`, so the deploy itself still reported success — the
probe is the only thing that reports this, and only if someone looks.

**The Git Bash trap.** Setting it from Git Bash on Windows silently produces a broken value:

```bash
railway variables --set "MEDIA_ROOT=/data/media"      # WRONG from Git Bash
# stores: MEDIA_ROOT=C:/Program Files/Git/data/media

MSYS_NO_PATHCONV=1 railway variables --set "MEDIA_ROOT=/data/media"   # correct
```

MSYS rewrites anything that looks like a Unix absolute path before the CLI sees it. The
stored value is then absolute on Windows but not on Linux, so `/healthz/` moves from
`inside_base_dir` to `not_absolute` — a different error that looks like the fix failed
rather than like the value was mangled. `MSYS_NO_PATHCONV=1` is already required for
`railway service files upload` below, for the same reason.

Verify after setting, always — read the value back rather than trusting the write:

```bash
railway variables --kv | grep '^MEDIA_ROOT='
curl -s https://velolog-production.up.railway.app/healthz/
```

## Rollback

Railway has no atomic rollback command for this setup. To roll back:

1. Find the last known-good deployment ID in the table above.
2. In the Railway dashboard → service → Deployments tab, locate that deployment and use **Redeploy** on it (or `railway service redeploy` if it's still the most recent successful build).
3. If the rollback needs a schema revert too (not just a code revert), restore the SQLite backup taken before the migration — see **Restore** below.

## SSH alias (one-time setup)

After registering an SSH key with Railway (`railway ssh keys add`), generate a permanent
`~/.ssh/config` alias for the service so `ssh`/`scp`/`sftp` work directly, without going
through `railway ssh`:

```bash
railway ssh config --service VeloLog --alias railway-velolog
```

Then connect with `ssh railway-velolog`.

## Backup — before running a schema migration in production

**Two** things live on the mounted Volume and both have to be captured: the SQLite
database at `/data/db.sqlite3`, and the uploaded GPX files under `/data/media`. Backing
up only the database restores a set of trips whose routes 404.

Requires an SSH key registered with Railway (`railway ssh keys add`, see the
`deploy/phase-2-env-settings` branch history for the one-time setup).

Backups are kept locally under `backup/` — gitignored in full, not just `backup/db/`.
Never commit either dump: the database holds password hashes and email addresses, and a
media dump is a copy of every rider's GPX files, which are the routes to and from their
homes.

In Git Bash on Windows, MSYS path conversion mangles the leading `/data/...` remote path
into a Windows path unless disabled with `MSYS_NO_PATHCONV=1`:

```bash
# Database
mkdir -p backup/db
MSYS_NO_PATHCONV=1 railway service files download /data/db.sqlite3 ./backup/db/backup-$(date +%Y%m%d-%H%M%S).sqlite3

# Uploaded GPX files (a directory — `railway service files download` takes either)
mkdir -p backup/media
MSYS_NO_PATHCONV=1 railway service files download /data/media ./backup/media/media-$(date +%Y%m%d-%H%M%S)
```

Run both immediately before any deploy that includes a migration, and keep them until
the deploy is confirmed healthy via `/healthz/`.

**Take the media backup seriously even when nothing looks wrong.** Writes to the Volume
depend on the `RAILWAY_RUN_UID=0` workaround; if that regresses, a non-root container's
writes silently do not persist rather than erroring
(`context/foundation/infrastructure.md:59`). Uploads then appear to succeed and vanish on
the next redeploy. `/healthz/` now performs a real media write/read/delete round-trip and
returns `"media": "error"` when that happens, so check it after every deploy — it is the
only signal that failure mode gives.

## Restore — Volume or host incident

Restore both halves, from the same point in time. A database restored ahead of the media
directory leaves `GpxTrack` rows pointing at files that are not there — the trip detail
page renders a route while its download 404s, which is exactly the silent-failure state
the app is built to avoid.

**Both commands below were wrong until the 2026-08-26 drill.** The corrections are not
cosmetic — the old ones failed outright or silently restored nothing. See *Restore drill*
below for what each one actually did.

1. Confirm the app is stopped or accepting no writes (avoid clobbering concurrent writes during restore).
2. Upload the last good database backup over the live file. **`--overwrite` is required** —
   without it the CLI refuses with "Remote path already exists" and the restore does not happen:
   ```bash
   MSYS_NO_PATHCONV=1 railway service files upload --overwrite ./backup/db/backup-<timestamp>.sqlite3 /data/db.sqlite3
   ```
3. Upload the matching media backup. **Upload the `gpx` child directory, not the backup
   wrapper** — for a directory upload the CLI treats REMOTE_PATH as the *parent* and appends
   the local directory's basename, so passing the wrapper creates
   `/data/media/media-<timestamp>/` and restores nothing Django can see:
   ```bash
   MSYS_NO_PATHCONV=1 railway service files upload --overwrite ./backup/media/media-<timestamp>/gpx /data/media
   ```
   Verify the destination afterwards — `railway service files list /data/media` must show
   `gpx/`, and no directory named after the backup timestamp.
4. Redeploy (or restart) the service so gunicorn picks up the restored files, then verify
   via `/healthz/` — a `200` with both `"database": "ok"` and `"media": "ok"` is the
   check. Then open a trip that had a route and confirm its download returns the file.

### Restore drill — 2026-08-26 (discharges engineering-backlog E-05)

Run against production while it held two test trips and no data worth losing, which is the
cheapest this drill will ever be. Sequence: back up both halves with tracks present, restore
an earlier snapshot to simulate losing them, confirm the loss, restore the good backup,
redeploy, confirm recovery.

**It worked, and the runbook did not.** Three defects, all of which would have surfaced for
the first time during a real incident:

| What was documented | What actually happened |
|---|---|
| `files upload <db> /data/db.sqlite3` | Refused: *"Remote path already exists. Use --overwrite"*. The restore silently did not occur; only the CLI's exit message said so. |
| `files upload <media-dir> /data/media` | Created `/data/media/<backup-name>/` and left the live files untouched. Reported success. A real restore would have looked fine and recovered nothing. |
| `--overwrite` fixes both | It fixes the file case only. Directory uploads still nest — the flag replaces `REMOTE_PATH`, and for a directory `REMOTE_PATH` is the parent. |

What the drill did prove, once the commands were corrected: the database restored exactly
(2 trips / 0 tracks → 2 trips / 2 tracks), the media restore landed at `/data/media/gpx`, a
redeploy (`9c1e188b`, previous deployment `REMOVED`) left both GPX files intact on the
Volume, and `/healthz/` returned `{"status": "ok", "database": "ok", "media": "ok"}`
throughout.

**Still not covered: there is no scratch-target restore path.** Everything above restores
over live production, so the only way to rehearse it is to risk the real thing. That was
acceptable on 2026-08-26 because production held nothing of value; it will not be acceptable
next time. A scratch path — a second Railway environment, or a local restore verified with
`manage.py` — should exist before the next drill.

**Agents cannot delete files here.** `railway service files delete` is refused for
non-humans, so cleaning up after a botched restore needs a person:
```bash
MSYS_NO_PATHCONV=1 railway service files delete -y /data/media/<stray-path>
```
Do not copy the command out of the CLI's own refusal message — it suggests
`files delete --service <name> <path>`, which does not parse. `-s/--service` is an option
on the `service files` parent, before the subcommand, and is unnecessary when a service is
already linked. `MSYS_NO_PATHCONV=1` is required from Git Bash for the same reason it is
everywhere else on this page.

## Orphaned media files — detect and reclaim

An orphan is a file under `MEDIA_ROOT` that no `GpxTrack` row points at. It costs Volume
space and nothing else — no page breaks, no request fails — so this is housekeeping, not an
incident. It is placed here, immediately after the restore material, because the two most
likely ways to create a lot of orphans at once are both restore procedures: nesting the media
upload under a wrapper directory (the drill's second defect, above), and restoring one half
without the other.

**Detect. This is read-only and always safe to run:**

```bash
railway ssh
uv run python manage.py reconcile_media
```

It walks the whole of `MEDIA_ROOT` — not just `gpx/` — because restore nesting writes outside
it by construction. Per-file lines go to stderr, the tally to stdout, so both land in
`railway logs` as plain text. Report-only is the default: it removes nothing and says so.

**Age threshold.** A file written seconds ago by a request still mid-save is
indistinguishable from an orphan by set difference alone, so anything modified within
`--min-age-minutes` (default 60) is reported as *spared*, not as an orphan. The same guard
applies to directories, which is what keeps a prune off a directory an upload has just
created and not yet written into. `--min-age-minutes 0` disables it — only on a service that
is genuinely idle, never on live production taking uploads.

### Before `--delete` — the precondition

`--delete` is the only irreversible action on this page. There is no undo on the Volume.

**Never reclaim while the database and the Volume may be from different points in time.**
The command's answer is `walk(MEDIA_ROOT) - {referenced keys}`, which names orphans only if
both halves describe the same moment. In practice that means:

- **Not after restoring either half**, until both are restored and `/healthz/` returns
  `"database": "ok"` and `"media": "ok"` — see the point-in-time warning that opens
  *Restore*, above. A database restored ahead of its media makes every file on the Volume
  look unreferenced.
- **Not with a `MEDIA_ROOT` whose value has not been confirmed.** A misconfigured
  `MEDIA_ROOT` (the failure this repo escalated to a Hard Rule) points the walk at a tree
  this database does not describe, and every file in it looks orphaned.
- **Never stage a backup, export, or scratch copy inside `MEDIA_ROOT`.** The referenced set
  is `GpxTrack.file` alone and the walk is deliberately unscoped to the whole Volume, so any
  file placed there that is not a `GpxTrack.file` looks exactly like an orphan — worse still
  if it is a symlink, since `--delete` would then reclaim whatever it points at.

The command catches the *complete* version of both states on its own: if it found files and
**not one of them is referenced**, `--delete` refuses, names the two likely causes, removes
nothing, and exits 0. `--allow-full-sweep` overrides that refusal and is correct only when
the database really is empty — never as a way past a refusal you did not expect. A refusal
you cannot explain means stop and find out why, not add the flag.

**The refusal does not cover a partial restore.** Restore a stale database that still has
*some* rows and the guard sees a referenced file, stays quiet, and offers to reclaim every
file belonging to the rows that snapshot is missing. Nothing in the walk can detect that,
which is why the precondition above is the operator's responsibility and not the command's.

**Reclaim, once the precondition holds:**

```bash
railway ssh
uv run python manage.py reconcile_media --delete
```

Files first, then the directories they emptied, deepest-first — `os.rmdir` refuses a
non-empty directory, so the prune cannot over-reach, and `MEDIA_ROOT` itself is never a
candidate. A per-file or per-directory failure is a counted skip in the tally, not an abort.
Re-running is a clean no-op.

### Why from inside the container, and not through the CLI

`railway service files delete` is refused for non-human callers (see *Restore*, above), and
`context/foundation/infrastructure.md` gates Volume changes made from outside the app. A
management command running inside the container **is the app acting on its own storage**,
which clears both — and unlike a hand-rolled `railway service files list` walk, it can see
the database, so it can tell a referenced file from an orphan at all. That is the difference
this command exists to make.

### Baseline measurement — 2026-08-28

Taken before any of this shipped, by a hand-rolled `railway service files list` walk plus a
production database download:

| | Rows | Files | Orphans |
|---|---|---|---|
| Production | 4 | 4 | 0 (exact in both directions) |
| Local | 3 | 3 | 0 files; 4 empty `gpx/<owner>/<trip>/` directories |

Production held **1.38 MiB on a 500 MB Volume**. That 500 MB is the only capacity figure
recorded anywhere for this deployment — it is not in `.railway/railway.ts`, the PRD, or any other
document in this repo, so it lives here. At the measured rate, capacity is not what makes
orphans worth reclaiming; knowing the number is.

## Production superuser (one-time)

**Status: created (2026-08-23).** Django admin is reachable in production.

No `createsuperuser` step exists in `.railway/railway.ts`, `DEPLOY.md`, or `deployment-plan.md`,
so this must be re-run manually if it's ever needed again:

```bash
railway ssh
uv run python manage.py createsuperuser
```

Store the credentials in the password manager — never in the repo or in `DEPLOY.md`.
Re-run only if the production database is ever rebuilt from scratch (a restore from a
pre-superuser backup, or a fresh Volume).

## Spend alert

A $5 Hobby-plan usage alert was set in Railway account billing settings during Phase 0.2 — confirm it's still active after any billing-related change.

**Open item (2026-08-21):** not re-verified as part of Phase 7 — check Railway dashboard → account → billing next time this file is touched.

## Static assets — a manifest failure is a site-wide outage

`.railway/railway.ts` `&&`-chains `collectstatic` ahead of `migrate` and gunicorn, so the app only
ever boots after the manifest exists. Keep it that way: since the map slice,
`templates/base.html` links the stylesheet unconditionally, so **every** page resolves
through staticfiles storage — before it, none did.

Under `CompressedManifestStaticFilesStorage` an absent or incomplete `staticfiles.json`
raises on any reference it cannot resolve, which is a 500 on every route, not a broken map
on one. The boot-time chain is the whole mitigation: it converts that into a deploy that
fails loudly and leaves the previous instance serving, rather than a live site quietly
500ing. Recover it like any failed deploy — **Rollback** above.

The CI `gates` job runs the same `collectstatic` before the test step, so an unresolvable
reference fails the pull request first. `tests/test_static_references.py` renders a page
through the production storage backend and *skips itself* when no manifest has been
collected, which is why that step order is load-bearing rather than cosmetic.

If a boot ever fails here, the fix is to vendor or correct the missing reference — never to
relax `WHITENOISE_MANIFEST_STRICT` or downgrade the storage class, which would trade this
loud failure for silently broken asset URLs in production.

## Third-party runtime dependency — OpenStreetMap tiles

Every trip page that has a route loads raster tiles from `https://tile.openstreetmap.org`
(`gpx/static/gpx/map.js`). Leaflet itself is vendored, so this is the only remote host the
app talks to at runtime, and it is browser-side only — there is no server-side call, so an
OSM outage draws the route over blank tiles rather than failing the page or the deploy.

Three things that follow, none of which the code can tell you:

- **The OSM Tile Usage Policy applies to this app.** It is a free community service, not a
  CDN with an SLA, and it asks that applications be identifiable and not bulk-download.
  Single-user personal traffic is comfortably inside it; if usage ever grows past that,
  the policy — not an error message — is what changes first. Switching to a paid tile host
  is a one-line change to the tile URL and its `attribution` in `map.js`.
- **Each map view sends a viewer's IP and the tile coordinates of a private route to a
  third party.** The trip URL itself is not sent: Django's `SECURE_REFERRER_POLICY` default
  of `same-origin` is what stops it. That default is load-bearing here — relaxing it leaks
  trip URLs to the tile host.
- **A CSP would work today and is worth adding before it stops being free.** The map page
  carries zero inline script (the config arrives via `json_script`, and
  `tests/trips/test_trip_detail_map.py` pins that as a structural invariant), so
  `script-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; style-src 'self'`
  would pass as the app stands — the `data:` is not optional, Leaflet uses an inline
  base64 GIF as its empty-tile placeholder. There is no CSP in `velo_log/settings.py`
  yet. Add one while the no-inline-script property still holds — the first inline handler
  anyone adds closes that door quietly.
