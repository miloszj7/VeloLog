# Deploy Runbook

## Known-good deployments

Update this table after every production deploy.

| Date | Deployment ID | Notes |
|---|---|---|
| 2026-08-21 | `fe1df79b-aa06-49b2-8965-15f16992cfe4` | First production deploy (Phase 5). `collectstatic` + `migrate` + gunicorn all succeeded; `/healthz/` returns 200 with a real DB write/read round-trip on the mounted Volume. |
| 2026-08-22 | `365f39af-95a3-403a-8f78-14fb4aa162c1` | Ships S-01 (`user-registration-login`) — register/log in/log out. Verified via `railway status` (service Online) and `/healthz/` returning `{"status": "ok"}`. |
| 2026-08-23 | `f2197620-9267-4a92-b9e2-40abbf84b9fa` | Ships S-02 (`create-and-list-trips`) — create/list trips. Verified via `railway status` (deployment status `SUCCESS`, instance `RUNNING`). |

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

1. Confirm the app is stopped or accepting no writes (avoid clobbering concurrent writes during restore).
2. Upload the last good database backup over the live file:
   ```bash
   MSYS_NO_PATHCONV=1 railway service files upload ./backup/db/backup-<timestamp>.sqlite3 /data/db.sqlite3
   ```
3. Upload the matching media backup over the live directory:
   ```bash
   MSYS_NO_PATHCONV=1 railway service files upload ./backup/media/media-<timestamp> /data/media
   ```
4. Redeploy (or restart) the service so gunicorn picks up the restored files, then verify
   via `/healthz/` — a `200` with both `"database": "ok"` and `"media": "ok"` is the
   check. Then open a trip that had a route and confirm its download returns the file.

## Production superuser (one-time)

**Status: created (2026-08-23).** Django admin is reachable in production.

No `createsuperuser` step exists in `railway.json`, `DEPLOY.md`, or `deployment-plan.md`,
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
