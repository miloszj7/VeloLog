# Quality Gate Structure

> How the project's lint/format/type/test checks are distributed across the local
> and CI layers, and why each check lives where it does. Edit-in-place per
> `context/foundation/README.md`'s convention — this isn't a point-in-time report.

Companion to `context/foundation/test-plan.md` §5 (which defines *what* must pass
before production) and `~/.claude/rules/git-workflow.md` (rebase/merge conventions).
This doc is about *where* each check runs, not what it checks for.

## Tool inventory

| Tool/check | Config | Layer(s) it runs at today |
|---|---|---|
| `black` | `pyproject.toml` `[tool.black]`, line-length 100 | post-edit (agent hook), pre-commit, CI (`--check`) |
| `ruff` | `[tool.ruff]` | pre-commit (`--fix`), CI (`check .`) |
| `isort` | `[tool.isort]` | pre-commit, CI (`--check-only`) |
| `mypy --strict` (+ django-stubs) | `[tool.mypy]` | pre-commit (staged files only), pre-push (whole project), CI |
| `pytest --cov` (`fail_under=80`) | `[tool.pytest.ini_options]` | pre-push, CI |
| `pytest -m bite_proof` (suite-credibility harness) | deselected by default `addopts` | pre-PR (manual), CI (`Suite credibility` step) |
| `tests/test_assertion_strength.py` | runs inside `pytest --cov`, no marker | wherever `pytest --cov` runs |
| `tests/test_ownership_matrix.py` | asserts route inventory against URLconf | wherever `pytest` runs |
| vendored-asset integrity (`sha256sum -c`) | `gpx/static/gpx/vendor/SHA256SUMS`, `static/vendor/bootstrap/SHA256SUMS` | pre-PR (manual), CI (first step) |
| `manage.py check` | Django system checks | pre-push, CI |
| `makemigrations --check --dry-run` | migration guard | pre-push, CI |
| `collectstatic --noinput` | must precede the test step (manifest-dependent test) | pre-PR (manual), CI |
| `pip-audit` | `continue-on-error: true` — report, not gate | CI only |

## Layer composition

Each gate sits at the cheapest layer that still catches it before the next layer
would — see `CLAUDE.md`'s "Task Router" for the reasoning.

| Layer | What runs | Config | Why here |
|---|---|---|---|
| **Post-edit** (Claude Code hook, agent loop only) | `black` on the single file just written/edited | `.claude/settings.json` `PostToolUse` | Only layer that feeds a fix back into the agent's context mid-turn. Kept to sub-second checks — anything slower blocks the edit loop on every save |
| **Pre-commit** | `ruff check --fix`, `black`, `isort` (all `stage_fixed: true` — auto-fix and re-stage), `mypy` on staged files | `lefthook.yml`, `pre-commit` group | Catches what bypassed the post-edit hook: manual edits, a teammate's commit, non-Claude-Code tooling. Staged-file scope keeps it to ~1-2s. **No `pytest` here** — measured: one test in `tests/trips/` costs ~0.95s, 5 costs ~3.6s, all 96 cost 117s — the cost is genuinely per-test (Django `TestCase` transaction/rollback overhead per test, not a one-time schema-build fixed cost), so there's no way to scope it down to "seconds" short of running almost nothing. `pytest-testmon` was tried as a change-impact test selector and rejected — see note below. All test execution lives at pre-push instead |
| **Pre-push** | `manage.py check`, migration guard, full `mypy .`, full `pytest --cov` | `lefthook.yml`, `pre-push` group | Heavier than pre-commit tolerates (whole-project mypy, full coverage-gated suite — measured 378 passed, 2 skipped in 328s); still local, still faster than waiting for CI to reject a push |
| **Pre-PR-creation** | `collectstatic --noinput`, `pytest -m bite_proof`, `sha256sum -c` on both vendor dirs | manual, via the `create-pr` skill checklist | The three checks that exist only in CI today. Running them once before opening a PR avoids a red CI run for something already knowable locally; too slow (bite-proof: ~12–13s of cold Django boots) to justify a git hook on every push |
| **Pre-merge** | Rebase onto `origin/master`, pre-merge history review, then re-run the pre-push set against the rebased tip if `master` moved | `~/.claude/rules/git-workflow.md` (existing convention) | Natural point to re-verify against a target branch that moved since the last local check |
| **CI** | Everything, unconditionally: asset integrity → lint/format/isort → mypy → `manage.py check` → migration guard → collectstatic → `pytest --cov` → `pytest -m bite_proof` | `.github/workflows/deploy.yml` `gates` job | Source of truth — runs regardless of what local layers did or skipped (a clone without hooks installed, a direct push). Local layers don't replace it; they cut the round-trips to it |

## Why Lefthook over the Python `pre-commit` framework

Both are viable; Lefthook fits this repo specifically because it has no
environment-isolation layer of its own — hooks just shell out to `uv run <tool>`,
reusing the exact venv and `uv.lock`-pinned versions that CI and the post-edit hook
already use. The `pre-commit` framework pins each hook's tool version separately in
`.pre-commit-config.yaml`, which would be a second source of truth alongside
`pyproject.toml`'s `dependency-groups.dev` — the two can drift. Lefthook also skips
`pre-commit`'s "install hook environments" step (network-dependent, per-hook Python
envs) since it has none.

## Rejected: `pytest-testmon` for pre-commit test selection

Tried and measured, not adopted. `pytest-testmon` re-runs only the tests whose
recorded coverage overlaps the changed lines, tracked in a local `.testmondata`
cache. On this repo it delivered **no speedup**: a cold run over `tests/trips/`
(building the baseline) took 115s; a second run with **zero source changes**
still re-selected and re-ran all 96 tests in 127s — testmon's cache wasn't
narrowing anything, most likely because Django's app registry import graph makes
nearly every test dependency-linked to `settings.py`/`apps.py` under line
coverage. Combined with the per-test cost already being the bottleneck (not a
one-time fixed setup — see the pre-commit row above), a selector that doesn't
actually narrow the test set buys nothing. Removed after the experiment
(`uv remove --dev pytest-testmon`, `.testmondata` deleted). Revisit only with a
concrete change (e.g. splitting settings into narrower modules) that would let
testmon's dependency graph actually stay small.

## Setup

`lefthook` is a dev dependency (`uv add --dev lefthook`, already in
`pyproject.toml`). After cloning the repo:

```bash
uv sync
uv run lefthook install
```

This wires `.git/hooks/pre-commit` and `.git/hooks/pre-push` to run `lefthook.yml`'s
two command groups. `uv run lefthook validate` checks the config's syntax without
running anything.
