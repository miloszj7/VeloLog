"""Fail the build if a first-party app is invisible to coverage.

`[tool.coverage.run] source` and `omit` in `pyproject.toml` are hand-maintained. A
first-party app added to `INSTALLED_APPS` without a matching entry in `source` is
invisible to coverage, and an app wholesale-excluded via `omit` is invisible even if
it *is* in `source` — either way `fail_under` passes regardless of how untested that
app's code is.
"""

import tomllib
from pathlib import Path

from velo_log.settings import INSTALLED_APPS

REPO_ROOT = Path(__file__).resolve().parent.parent


def _wholesale_omitted_apps(omit_entries: set[str]) -> set[str]:
    """Return top-level packages that `omit` excludes in their entirety.

    A file-scoped entry like `velo_log/wsgi.py` omits one module, not the package —
    those are left alone. Only an entry equal to the package name itself, or a glob
    covering everything under it (`app/*`, `app/**`), counts as wholesale.
    """
    wholesale = set()
    for entry in omit_entries:
        parts = entry.split("/")
        if len(parts) == 1:
            wholesale.add(parts[0])
        elif len(parts) == 2 and parts[1] in ("*", "**"):
            wholesale.add(parts[0])
    return wholesale


def test_installed_apps_are_covered() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        pyproject = tomllib.load(f)
    coverage_run = pyproject["tool"]["coverage"]["run"]
    coverage_source = set(coverage_run["source"])
    coverage_omit = set(coverage_run.get("omit", []))

    first_party_apps = {
        top_level
        for app in INSTALLED_APPS
        if (REPO_ROOT / (top_level := app.split(".")[0])).is_dir()
    }

    missing = first_party_apps - coverage_source
    assert not missing, (
        f"{sorted(missing)} — installed but missing from "
        "[tool.coverage.run] source in pyproject.toml. Add the missing package(s) "
        "there or coverage silently ignores their code."
    )

    wholesale_omitted = _wholesale_omitted_apps(coverage_omit) & first_party_apps
    assert not wholesale_omitted, (
        f"{sorted(wholesale_omitted)} — installed app(s) excluded in their entirety via "
        "[tool.coverage.run] omit in pyproject.toml, which hides them from coverage even "
        "though they're listed in source. Remove the wholesale omit entry or scope it to "
        "specific files."
    )
