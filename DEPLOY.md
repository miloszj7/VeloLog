# Deploy Runbook

## Known-good deployments

| Date | Deployment ID | Notes |
|---|---|---|
| 2026-08-21 | `fe1df79b-aa06-49b2-8965-15f16992cfe4` | First production deploy (Phase 5). `collectstatic` + `migrate` + gunicorn all succeeded; `/healthz/` returns 200 with a real DB write/read round-trip on the mounted Volume. |

<!-- Phase 7 will expand this file with rollback/backup/restore procedures. -->
