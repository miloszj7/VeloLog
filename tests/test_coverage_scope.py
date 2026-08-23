"""Fail the build if a first-party app is invisible to coverage.

`[tool.coverage.run] source` in `pyproject.toml` is hand-maintained. A first-party
app added to `INSTALLED_APPS` without a matching entry in `source` is invisible to
coverage — `fail_under` passes regardless of how untested that app's code is.
"""

import tomllib
from pathlib import Path

from velo_log.settings import INSTALLED_APPS

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_installed_apps_are_covered() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        pyproject = tomllib.load(f)
    coverage_source = set(pyproject["tool"]["coverage"]["run"]["source"])

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
