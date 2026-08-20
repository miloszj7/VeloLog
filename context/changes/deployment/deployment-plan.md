# VeloLog — Deploy to Railway (phased plan)

## Context

`context/foundation/infrastructure.md` already picked **Railway** (over Fly.io, despite `tech-stack.md`'s earlier `deployment_target: fly` hint — infra research superseded that hint after scoring both) as the deploy target for VeloLog, a solo-dev, 2-week Django 6.0.5 / Python 3.14 / uv / SQLite MVP with a $5/mo budget ceiling. The repo today is **just the `django-admin startproject` stub** (commit `1913e0b "Bootstrap - working stub"`) — no custom app, no production settings, no Dockerfile/Procfile, no CI, **no GitHub remote, and none of the required CLIs installed locally**. This plan turns the infra doc's "Getting Started" section into an ordered, independently-committable sequence, corrected against Railway's **current** docs (verified via live research on 2026-08-20 — some of the infra doc's specifics are already stale), starts with the account/tooling setup the rest of the plan assumes, and is extended with a CI/CD phase per `tech-stack.md`'s `ci_provider: github-actions` / `ci_default_flow: auto-deploy-on-merge` hint.

**Corrections to `infrastructure.md` found during doc research (apply these, not the older names):**
- Railway's current builder is **Railpack**, not Nixpacks (Nixpacks is in maintenance mode since March 2026). Railpack auto-detects `pyproject.toml` + `uv.lock` with zero config — this *de-risks* infra doc's Nixpacks/uv-detection concern, it doesn't need a Dockerfile fallback for that reason alone.
- Python version pin env var is **`RAILPACK_PYTHON_VERSION`**, not `NIXPACKS_PYTHON_VERSION`.
- Python 3.14 support is not explicitly enumerated in Railpack docs — only "not-EOL Python versions" as a floor policy. Must be verified with a real trial build (Phase 1), not assumed.
- CLI command is **`railway variable set KEY=value`** (singular "variable"), not `railway variables set`.
- `RAILWAY_RUN_UID=0` for non-root containers writing to a Volume is still current/correct — no newer official pattern exists.
- There is no official Railway GitHub Action — the standard CI pattern is running the Railway CLI (`ghcr.io/railwayapp/cli:latest`) in a workflow step, authenticated via a `RAILWAY_TOKEN` secret.
- Prefer `railway.json` (`deploy.startCommand`) over a `Procfile` as the authoritative start-command mechanism — Railway docs state code-based config always overrides dashboard values, and `railway.json` is the more explicit, versioned form.

**Local environment audit (checked 2026-08-20):** Node v26.7.0 and npm 11.19.0 are already present (needed to install the Railway CLI). Missing: no `git remote` configured on this repo, Railway CLI, GitHub CLI (`gh`), and Docker are all absent from PATH. Phase 0 below covers all of these gaps.

## Phase 0 — Prerequisites: accounts & local tooling

Goal: get every account and CLI the rest of the plan depends on in place, once, before any repo changes start. All steps here are one-time setup, mostly manual/human (account creation, OAuth, payment details) — an agent can run the CLI install/verify commands but account signup and card entry must be done by the developer in a browser.

### 0.1 GitHub — push the repo to a remote

The repo has no `git remote` yet; Phase 6 (CI/CD) and Railway's own GitHub-based deploy option both need one.

1. Create an empty repository on GitHub (github.com → New repository — do **not** initialize with a README/`.gitignore`, this repo already has its own).
2. Locally: `git remote add origin https://github.com/<user>/<repo>.git`
3. `git push -u origin main`
4. Optional but convenient: install **GitHub CLI** (`gh`) so repo/secret management can be scripted instead of using the web UI — on Windows: `winget install --id GitHub.cli` (or `scoop install gh`), then `gh auth login`. Not strictly required — every `gh` step below has a web-UI equivalent — but saves round-trips once Phase 6 needs to set the `RAILWAY_TOKEN` repo secret.

### 0.2 Railway — account signup

1. Sign up at railway.com. **Recommended: sign up via "Continue with GitHub"** (not email) — this links the same GitHub identity used in 0.1 and makes the optional GitHub-integration deploy path (auto-deploy on push, as an alternative/supplement to the Phase 6 Actions workflow) a one-click "Deploy from GitHub repo" instead of a separate connection step later.
2. Upgrade to the **Hobby plan** ($5/mo, includes $5 usage credit) in account billing settings — a payment card is required even though usage is expected to stay within the included credit. This matches the infra doc's assumed budget ceiling; do this deliberately, not as a surprise mid-deploy prompt.
3. In the dashboard, set a usage/spend alert at the $5 credit threshold now, while account setup is already open (pulled forward from the old Phase 3 — no reason to defer a 30-second setting).

### 0.3 Railway CLI — install & authenticate locally

Node/npm are already installed, so the simplest path applies directly:

1. `npm i -g @railway/cli`
2. Verify: `railway --version`
3. `railway login` — opens a browser to complete OAuth against the account created in 0.2.
4. From the repo root: `railway init` to create a new Railway project (or `railway link` if one was already created via the dashboard's "Deploy from GitHub repo" flow in 0.2) — this produces the project link Phase 1 builds on.

### 0.4 Docker — optional, only if the Railpack build spike fails

Not installed locally, and not needed unless Phase 1's build spike shows Railpack can't handle Python 3.14 or the `uv` toolchain and a custom Dockerfile fallback is required. If that happens: install Docker Desktop (docker.com) to build/test the Dockerfile locally before pushing it to Railway. Skip this step entirely if Phase 1 succeeds without it — don't install speculatively.

**No commit from this phase** — it's accounts + local CLI state, not repo content, except the `git push -u origin main` in 0.1 which puts the existing stub on GitHub for the first time.

## Phase 1 — De-risk the build before touching app code

Goal: confirm Railway can actually build this exact stack before investing in settings/CI work. Cheapest possible spike.

1. Add a `.python-version`-respecting pin explicitly via `RAILPACK_PYTHON_VERSION=3.14` project variable (belt-and-suspenders alongside the existing `.python-version` file) — `railway variable set RAILPACK_PYTHON_VERSION=3.14`.
2. `railway up` with the stub as-is (no Procfile/settings changes yet) and inspect `railway logs --build` to confirm Railpack detects `uv.lock` and installs Python 3.14 + Django cleanly.
3. If Railpack fails to detect Python 3.14 or the uv toolchain: fall back to a minimal custom `Dockerfile` (multi-stage: `python:3.14-slim` build stage running `uv sync`, slim runtime stage) — write it now rather than mid-Phase-3, using Docker (Phase 0.4) to test it locally first.
4. Report result; do not proceed to Phase 2 until the base build succeeds.

**Stop condition / commit:** nothing app-facing changes yet — this phase only proves the build path. Record the outcome (Railpack worked / Dockerfile fallback needed) before continuing.

## Phase 2 — Production-ready Django settings (env-driven config)

Goal: make `velo_log/settings.py` deployable anywhere via environment variables, per the Python security baseline (no hardcoded secrets) and `~/.claude/rules/python.md`'s config-split convention.

Files: `velo_log/settings.py`, `pyproject.toml` (add `django-environ` or use stdlib `os.environ` — prefer `django-environ` for `DATABASE_URL`-style parsing since a future Postgres migration is plausible), `.env.example` (new, committed), `.env` (new, local-only, already gitignored).

1. `SECRET_KEY` — read from `SECRET_KEY` env var, generate a real value for `.env` (local) and Railway variables (prod); no fallback to the insecure default in production.
2. `DEBUG` — env-driven, default `False`; explicitly set `DEBUG=True` in local `.env` only.
3. `ALLOWED_HOSTS` — env-driven comma-separated list; Railway's dynamic domain must be included in production.
4. `DATABASES["default"]["NAME"]` — env-driven path (e.g. `DB_PATH` defaulting to `BASE_DIR / "db.sqlite3"` locally, pointed at `/data/db.sqlite3` under the Railway Volume in prod).
5. Add `STATIC_ROOT` and confirm `STATIC_URL`; add `whitenoise` (`uv add whitenoise`) to `MIDDLEWARE` for static file serving — Railway has no separate static host, so app-served static via whitenoise is the correct fit for this scale.
6. Add `.env.example` documenting every required var (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_PATH`) with no real values, per the Python rules' config-split convention.

**Commit:** "Add env-driven production settings (SECRET_KEY, DEBUG, ALLOWED_HOSTS, DB path, static files)".

## Phase 3 — Deploy artifacts

Goal: give Railway a deterministic, explicit start command and production WSGI server.

1. `uv add gunicorn`.
2. Add `railway.json` at repo root:
   ```json
   {
     "$schema": "https://railway.com/railway.schema.json",
     "deploy": {
       "startCommand": "uv run python manage.py migrate && uv run gunicorn velo_log.wsgi --bind 0.0.0.0:$PORT"
     }
   }
   ```
   (No `Procfile` — avoid shipping both to prevent ambiguity per Railway's own config-precedence note.)
3. If Phase 1 required a Dockerfile fallback, wire `railway.json`'s `build` section (or `builder: DOCKERFILE`) accordingly instead.

**Commit:** "Add gunicorn + railway.json deploy config".

## Phase 4 — Railway project provisioning

Goal: attach persistent storage and configure secrets — matches infra doc's Getting Started steps 4 & 6, corrected for current CLI/env-var names.

1. `railway volume add` — mount at `/data`.
2. Set project variables via `railway variable set`: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=<railway-domain>`, `DB_PATH=/data/db.sqlite3`, `RAILWAY_RUN_UID=0` (required so the app can write to the root-owned Volume mount — flag this in a code comment or the deploy doc as a known Railway quirk, not a security choice).
3. Spend alert was already set in Phase 0.2 — just confirm it's still active.

**No commit needed** — this is Railway-side config, not repo state, except for documenting the required variable names (fold into Phase 2's `.env.example` if not already covered).

## Phase 5 — First production deploy + smoke test

1. `railway up`.
2. `railway logs` — confirm migration ran and gunicorn is serving.
3. Add a lightweight health-check path (e.g. Django's built-in admin `/admin/` login page, or a trivial `/healthz` view) and hit it over HTTPS to confirm `ALLOWED_HOSTS`/static files/DB write all work end-to-end — this also satisfies the risk register's "startup health check that performs a real write-and-read against the SQLite file" mitigation.
4. Record the deployment ID as the first "known-good" entry in a short runbook note (see Phase 7) — there is no atomic rollback command, so this manual record is the actual mitigation.

## Phase 6 — CI/CD: GitHub Actions auto-deploy on merge

Goal: satisfy `tech-stack.md`'s `ci_provider: github-actions` / `ci_default_flow: auto-deploy-on-merge` hint, using the verified current pattern (no official Action exists).

File: `.github/workflows/deploy.yml`

1. Generate a Railway **project token** (Railway dashboard → project → Settings → Tokens) — human-only step, not agent-automatable.
2. In the GitHub repo (created in Phase 0.1) → Settings → Secrets and variables → Actions, add that token as `RAILWAY_TOKEN` (via `gh secret set RAILWAY_TOKEN` if `gh` was installed in 0.1, or the web UI otherwise).
3. Workflow trigger: `push` to `main`.
4. Job runs in `ghcr.io/railwayapp/cli:latest` container (or installs the CLI in a standard runner), authenticates via the `RAILWAY_TOKEN` secret, and runs `railway up --service=<service-id>`.
5. Add a preceding `uv run python manage.py check` (or, once tests exist, `uv run pytest`) step as a merge gate before the deploy step — don't deploy on a broken build.
6. Per the infra doc's Approval note: this workflow deploys automatically on merge, which the developer already treats as pre-reviewed (PR review gates the merge, not the deploy) — no additional human-approval step inside the workflow itself.

**Commit:** "Add GitHub Actions workflow for auto-deploy to Railway on merge to main".

## Phase 7 — Operational hardening (runbook, not code)

Matches the infra doc's Risk Register mitigations that are process, not code:

1. Write a short `DEPLOY.md` (or fold into `README.md`) capturing: last known-good deployment ID (update after every prod deploy), manual SQLite backup command before running a schema migration in production, and the manual restore steps for a Volume/host incident.
2. Confirm the $5 Hobby spend alert (Phase 0.2 / Phase 4) is active.

**Commit:** "Add deploy runbook (rollback, backup, spend-alert notes)".

## Verification

- Phase 0: `railway --version` and `git remote -v` both resolve; `railway whoami` confirms the CLI is authenticated against the account created in 0.2.
- Phase 1: `railway logs --build` shows a successful Railpack build (or Dockerfile build) with Python 3.14 + uv deps installed.
- Phase 2–3: `uv run python manage.py check --deploy` locally passes (or lists only expected warnings) with `DEBUG=False` and a real `SECRET_KEY` set via `.env`.
- Phase 5: hitting the deployed URL's health-check path over HTTPS returns 200 and a fresh migration/DB write round-trips on the mounted Volume.
- Phase 6: a test merge to `main` triggers the workflow in the GitHub Actions tab and results in a new Railway deployment visible via `railway logs`.
