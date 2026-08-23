# Deploy Runbook

## Known-good deployments

Update this table after every production deploy.

| Date | Deployment ID | Notes |
|---|---|---|
| 2026-08-21 | `fe1df79b-aa06-49b2-8965-15f16992cfe4` | First production deploy (Phase 5). `collectstatic` + `migrate` + gunicorn all succeeded; `/healthz/` returns 200 with a real DB write/read round-trip on the mounted Volume. |
| 2026-08-22 | `365f39af-95a3-403a-8f78-14fb4aa162c1` | Ships S-01 (`user-registration-login`) — register/log in/log out. Verified via `railway status` (service Online) and `/healthz/` returning `{"status": "ok"}`. |

## Rollback

Railway has no atomic rollback command for this setup. To roll back:

1. Find the last known-good deployment ID in the table above.
2. In the Railway dashboard → service → Deployments tab, locate that deployment and use **Redeploy** on it (or `railway service redeploy` if it's still the most recent successful build).
3. If the rollback needs a schema revert too (not just a code revert), restore the SQLite backup taken before the migration — see **Restore** below.

## Backup — before running a schema migration in production

The SQLite file lives on the mounted Volume at `/data/db.sqlite3`. Requires an SSH key registered with Railway (`railway ssh keys add`, see the `deploy/phase-2-env-settings` branch history for the one-time setup).

```bash
railway service files download /data/db.sqlite3 ./backup-$(date +%Y%m%d-%H%M%S).sqlite3
```

Run this immediately before any deploy that includes a migration, and keep the backup file until the deploy is confirmed healthy via `/healthz/`.

## Restore — Volume or host incident

1. Confirm the app is stopped or accepting no writes (avoid clobbering concurrent writes during restore).
2. Upload the last good backup over the live file:
   ```bash
   railway service files upload ./backup-<timestamp>.sqlite3 /data/db.sqlite3
   ```
3. Redeploy (or restart) the service so gunicorn picks up the restored file, then verify via `/healthz/`.

## Production superuser (one-time)

No `createsuperuser` step exists in `railway.json`, `DEPLOY.md`, or `deployment-plan.md`,
so the Django admin (registered for `Trip` in S-02) is unreachable in production until
this runs once:

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
