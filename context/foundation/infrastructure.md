---
project: VeloLog
researched_at: 2026-08-20
recommended_platform: Railway
runner_up: Fly.io
context_type: mvp
tech_stack:
  language: Python 3.14
  framework: Django 6.0.5
  runtime: uv-managed, SQLite
---

## Recommendation

**Deploy on Railway.**

Railway is the only shortlisted platform with a full Pass on all five agent-friendly criteria (CLI-first, managed/serverless, agent-readable docs, stable deploy API, official MCP server), and its Hobby plan ($5/mo minimum, includes $5 usage credit) fits the developer's stated $5/mo budget ceiling. The interview ruled out Cloudflare, Vercel, and Netlify as hard-constraint failures — none of them can run a stock Django/SQLite process without a serverless/edge rearchitecture that this 2-week solo MVP has no budget for. Between the three viable PaaS candidates (Railway, Fly.io, Render), Railway scored highest and, unlike Render, does not force a trade-off between "free but sleeps" and "paid to stay awake."

## Platform Comparison

Hard-filtered out before scoring (fail the tech-stack hard constraint — no persistent WSGI process / SQLite support without a rearchitecture):

- **Cloudflare Workers/Pages** — Python Workers (Pyodide) is open beta; no first-party Django runtime; SQLite would need to move to D1 and uploads to R2 via unofficial community shims (`django-on-workers`).
- **Vercel** — Zero-config Django support is GA and DX is excellent, but the filesystem is read-only except an ephemeral, non-shared `/tmp` — breaks SQLite outright and forces a move to Postgres (Neon) + Vercel Blob before this app could run at all.
- **Netlify** — No persistent-process runtime at all (Functions only, 10s timeout on free tier); SQLite is a hard blocker the same way as Vercel, and Django itself isn't natively GA-supported (would need a WSGI adapter).

Scored (Pass / Partial / Fail per `references/agent-friendly-criteria.md`):

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP / Integration | Total |
|---|---|---|---|---|---|---|
| **Railway** | Pass | Pass | Pass | Pass | Pass | 5 Pass |
| Fly.io | Pass | Pass | Partial | Pass | Partial | 3 Pass / 2 Partial |
| Render | Partial | Pass | Pass | Partial | Partial | 2 Pass / 3 Partial |

Notes per platform:

- **Railway** — `railway` CLI (GA) covers login/init/link/up/logs/redeploy. Docs publish `.md` pages and an `llms.txt` index. Deploy is deterministic (`railway up`); "rollback" is a redeploy targeting a prior deployment ID rather than a single atomic command, still Pass because it's scriptable and deterministic. Official Railway MCP server (GA, local via CLI or remote at `mcp.railway.com`) is the only fully first-party MCP among the three finalists.
- **Fly.io** — `flyctl` (GA) is mature and this project's `tech-stack.md` already named it as the intended target. Docs support a "copy as markdown" pattern but no confirmed official `llms.txt` at time of research (Partial). MCP integration exists only as a community wrapper (`superfly/flymcp`), not first-party (Partial).
- **Render** — Native Python runtime is GA and docs publish an official `llms.txt`/`llms-full.txt`, but rollback is dashboard-centric (CLI doesn't expose a first-class rollback command) and the platform's own "docs MCP" is explicitly marked experimental with a stated risk of discontinuation — both pulled the CLI and MCP scores down to Partial.

### Shortlisted Platforms

#### 1. Railway (Recommended)

Highest total score of the three viable candidates: full CLI coverage, official GA MCP server, Postgres and Volumes both GA and one-click, and docs published in agent-readable markdown with an `llms.txt` index. At this project's traffic (single user, occasional GPX uploads, testing only), the $5/mo Hobby plan's included credit is expected to cover actual usage — the $5 is effectively a flat minimum, not a metered surprise, at this scale.

#### 2. Fly.io

Runner-up: was already the assumed target in `tech-stack.md`, and its Docker-first deploy model is a very close technical match for Django. Docker-based deploy is first-class (`fly launch` auto-detects Django), and SQLite-on-Volume is an explicitly supported, documented pattern (single-machine, single-region — which matches this MVP's scope exactly). Loses to Railway only on documentation format and MCP maturity — both softer, non-blocking criteria. The free tier is gone (since Oct 2024), but a minimal always-on instance is estimated at ~$2-5/mo, comfortably inside the $5 budget.

#### 3. Render

Third: Django support is native and GA, and Render Disks make SQLite persistence straightforward, but rollback is dashboard-first (not a CLI verb) and attaching a Disk disables zero-downtime deploys — every deploy causes a brief outage. The $0 free tier exists but sleeps after 15 minutes of inactivity (30-60s cold start on next request), and free Postgres expires after 30 days — a real trap if picked over SQLite+Disk. Viable, but the weakest of the three on agent-driven operability.

## Anti-Bias Cross-Check: Railway

### Devil's Advocate — Weaknesses

1. SQLite on a Railway Volume requires an undocumented-in-the-getting-started-guide workaround (`RAILWAY_RUN_UID=0`) so a non-root container can write to the mounted volume — easy to misconfigure, and a misconfiguration fails silently (writes just don't persist) rather than erroring loudly.
2. Railway Volumes are single-instance and single-region, capped at 3,000 IOPS — a host or volume incident is a full outage for this app with no automatic failover, and recovery is a manual restore.
3. Nixpacks' Python/uv detection may lag behind Python 3.14 (a very recent release) or may not recognize `uv.lock`/`pyproject.toml` as cleanly as `requirements.txt` — a real risk of falling back to a custom Dockerfile, which erodes the "zero-config" DX advantage that helped Railway win the scoring.
4. There is no atomic, single-command "rollback to last known-good deploy" in the Railway CLI — recovery from a bad deploy means finding a deployment ID and redeploying it, which is slower and more error-prone under incident pressure than Fly's `fly deploy --image <prior>`.
5. Billing is metered per-second across vCPU/RAM/egress/volume storage — while low at this project's current scale, it is less predictable month-to-month than a flat-rate competitor if usage patterns (e.g., photo/GPX upload bursts) change.

### Pre-Mortem — How This Could Fail

The team deployed VeloLog (Django 6/SQLite/uv) on Railway, trusting that Nixpacks' auto-detection "just works." Six months in, it fell apart in stages. First, Nixpacks never reliably picked up `uv.lock`, so a stale pip-based build silently used the wrong Python version, ignoring the `.python-version` pin — the app worked locally but broke intermittently after platform-side rebuilds. Second, nobody had set `RAILWAY_RUN_UID=0` correctly from day one; the SQLite volume mount worked initially under the default root user, but a later base-image update changed the default user, and writes began failing silently — GPX upload records were quietly lost, violating the "data never lost" guardrail from the PRD. Third, a bad deploy shipped and there was no atomic rollback command — the developer spent 20 minutes in the dashboard hunting for the right deployment ID while the app 500'd. Finally, nobody was watching the metered bill, and a short burst of GPX/photo uploads pushed usage past the Hobby credit, triggering a surprise charge right as the project was gaining its first real users.

### Unknown Unknowns

- Whether Nixpacks cleanly detects a `uv`-managed project (vs. `requirements.txt`) is not confirmed in Railway's official docs — worth a real test deploy early, before committing further implementation around it.
- The `RAILWAY_RUN_UID=0` requirement for non-root containers writing to a Volume is documented only in community Q&A threads, not prominently in the main getting-started guide.
- Railway has no official atomic "rollback to previous deploy" CLI verb — recovery is a manual redeploy-by-ID, a materially different (slower) operational story than Fly.io's or Vercel's rollback commands.
- Metered per-second billing across CPU/RAM/egress/storage means cost is not flat — for a personal-diary MVP with bursty GPX/photo uploads, month-to-month cost can vary in ways a flat-rate plan wouldn't.
- Railway's Slack/Discord "Railway Agent" AI feature is brand-new (introduced July 2026) — treat it as unproven; rely on the stable CLI/MCP surface for real operations, not this feature.

## Operational Story

- **Preview deploys**: Railway generates a preview environment per pull request when PR environments are enabled on the project; each preview gets its own URL and can share or fork the production database's schema. No fork-PR restriction beyond normal GitHub repo permissions.
- **Secrets**: Environment variables and secrets live in the Railway project's Variables tab (or set via `railway variables set`); only project collaborators can view/edit them. Rotate by updating the variable and triggering a redeploy — no automatic rotation.
- **Rollback**: No atomic one-command rollback. Identify the last known-good deployment via `railway logs` / the dashboard's deployment history, then redeploy that specific deployment ID (`railway redeploy` targeting the ID, or via the dashboard). SQLite lives on a Volume, so a rollback of app code does not roll back data — if a bad migration already ran against the SQLite file, restoring correct behavior requires a manual data fix or a volume-level restore, not just a code rollback.
- **Approval**: A human should approve any production redeploy following an incident, any change to the Volume-mounted SQLite file outside the app itself, and any billing-plan change. An agent may safely run `railway logs`, `railway up` for routine non-incident deploys the developer has already reviewed, and read-only status checks via the MCP server.
- **Logs**: `railway logs` (optionally `--build` for build-time logs) tails runtime logs from the CLI; the official Railway MCP server (`mcp.railway.com` or local via CLI) exposes the same log data as a structured tool call for an agent, without needing to parse CLI text output.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| SQLite writes silently fail after a base-image update resets the container's default user, breaking the `RAILWAY_RUN_UID=0` workaround | Devil's advocate / Pre-mortem | M | H | Pin the Dockerfile's base image explicitly (no `latest`); add a startup health check that performs a real write-and-read against the SQLite file and fails loudly if it doesn't round-trip |
| Volume/host incident causes full outage with no automatic failover (single-instance, single-region) | Devil's advocate | L | H | Schedule a recurring `railway` volume backup/export of the SQLite file to external storage (e.g., a periodic job pushing to S3-compatible storage); document the manual restore steps before they're needed |
| Nixpacks fails to detect the `uv`-managed project correctly, or lags Python 3.14 support | Unknown unknowns / Research finding | M | M | Do a real trial deploy early in implementation (before business logic is built out) to confirm the build succeeds; keep a working custom Dockerfile as a fallback ready to commit if Nixpacks detection proves unreliable |
| No atomic rollback CLI command lengthens incident recovery time | Devil's advocate / Operational story | M | M | Keep a runbook note (deployment ID of last known-good release) updated after every successful production deploy, so redeploy-by-ID during an incident doesn't require first hunting through dashboard history |
| A bad deploy runs a migration that a code rollback can't undo, since SQLite data on the Volume is independent of app code | Operational story | L | H | Always take a manual SQLite file snapshot before running a schema migration in production; never treat "rollback the code" as equivalent to "undo the migration" |
| Metered per-second billing produces a cost spike from an unexpected traffic/upload burst | Devil's advocate / Pre-mortem | L | M | Set a Railway usage/spend alert at the $5 Hobby credit threshold so a spike is visible before it becomes a surprise bill, given this project's explicit $5/mo budget ceiling |

## Getting Started

1. Install the CLI and authenticate: `npm i -g @railway/cli` then `railway login`.
2. From the VeloLog repo root, link the project: `railway init` (or `railway link` if a Railway project already exists).
3. Add a `Procfile` at the repo root (Railway's Python auto-detection builds the app but does not infer a start command): `web: uv run python manage.py migrate && uv run gunicorn velo_log.wsgi --bind 0.0.0.0:$PORT`. Add `gunicorn` via `uv add gunicorn` first, since it isn't yet a dependency.
4. Attach a Volume for the SQLite database (`railway volume add`, mount at e.g. `/data`) and point `DATABASES["default"]["NAME"]` in `velo_log/settings.py` at a path under that mount via an env var; if the container's Dockerfile/build runs as a non-root user, set `RAILWAY_RUN_UID=0` as a project variable so the process can write to the mounted volume.
5. Deploy with `railway up`, then confirm with `railway logs` that migrations ran and the app is serving; set `DEBUG=False` and `ALLOWED_HOSTS` via Railway project variables before the first real deploy.
6. Set a usage/spend alert in the Railway dashboard at the $5 Hobby credit threshold, matching this project's stated budget ceiling.

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration
- CI/CD pipeline setup
- Production-scale architecture (multi-region, HA, DR)
