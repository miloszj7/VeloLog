"""Prove that an optional env var left blank resolves to its fallback, not to "".

django-environ returns a key's `default` only when the key is *absent* — present but
blank yields "". A blank arrives easily: a hand-edited `.env` keeping the key as a
reminder, or a deploy environment that defines it empty. For MEDIA_ROOT the result is
silent, since `FileSystemStorage` turns "" into `os.path.abspath("")`, the process CWD.
Uploads then land beside the source tree, where the `media/` gitignore entry does not
match them, and `/healthz/` stays green because the location guard is skipped under
DEBUG.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from velo_log.settings import BASE_DIR, env_or


def test_env_or_falls_back_when_the_key_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VELOLOG_PROBE", raising=False)

    assert env_or("VELOLOG_PROBE", "fallback") == "fallback"


def test_env_or_falls_back_when_the_key_is_present_but_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression: a key kept as a reminder, with no value filled in."""
    monkeypatch.setenv("VELOLOG_PROBE", "")

    assert env_or("VELOLOG_PROBE", "fallback") == "fallback"


def test_env_or_returns_a_real_value_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VELOLOG_PROBE", "/data/media")

    assert env_or("VELOLOG_PROBE", "fallback") == "/data/media"


def test_blank_keys_resolve_to_the_project_defaults(tmp_path: Path) -> None:
    """The wiring, not just the helper: both settings must survive a blank `.env`.

    Resolved in a subprocess because both are read at import time, and this suite's
    `conftest.py` re-points `MEDIA_ROOT` at `tmp_path` for every test — so nothing
    in-process can observe what a blank key actually produces. Run from a foreign cwd
    as well, since the failure mode being pinned is precisely a path that silently
    resolves against the working directory.
    """
    code = (
        "import django, json\n"
        "django.setup()\n"
        "from django.conf import settings\n"
        "print(json.dumps({'media_root': settings.MEDIA_ROOT,\n"
        "                  'db_name': settings.DATABASES['default']['NAME']}))\n"
    )
    # S603: argv is entirely literal — this interpreter and the constant source above.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        env={
            **os.environ,
            # cwd is deliberately foreign, so the repo root has to be put back on the
            # import path explicitly.
            "PYTHONPATH": str(BASE_DIR),
            "DJANGO_SETTINGS_MODULE": "velo_log.settings",
            "SECRET_KEY": "test-only-not-a-real-secret",
            "MEDIA_ROOT": "",
            "DB_PATH": "",
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    resolved = json.loads(result.stdout)
    assert resolved["media_root"] == str(BASE_DIR / "media")
    assert resolved["db_name"] == str(BASE_DIR / "db.sqlite3")


def test_blank_media_root_trips_the_guard_under_debug_false(tmp_path: Path) -> None:
    """Prove the two halves compose, not just that each is true in isolation.

    `test_env_or_falls_back_when_the_key_is_present_but_blank` (this file) proves the
    fallback lands on `BASE_DIR / "media"`; the sibling guard test in
    `tests/test_media_storage.py` proves that path trips the guard when hand-set.
    Neither proves a real process, booted with no `.env` and `DEBUG=False` — the exact
    shape of the 2026-08-26 production incident — reaches `inside_base_dir` on its own.
    This suite's autouse `_media_root_in_tmp_path` fixture (`tests/conftest.py`)
    prevents any in-process test from observing that composition, so a subprocess is
    the only way to see it.
    """
    code = (
        "import django\n"
        "django.setup()\n"
        "from velo_log.urls import media_root_misconfiguration\n"
        "print(media_root_misconfiguration())\n"
    )
    # S603: argv is entirely literal — this interpreter and the constant source above.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        env={
            **os.environ,
            # cwd is deliberately foreign, so the repo root has to be put back on the
            # import path explicitly.
            "PYTHONPATH": str(BASE_DIR),
            "DJANGO_SETTINGS_MODULE": "velo_log.settings",
            "SECRET_KEY": "test-only-not-a-real-secret",
            "DEBUG": "False",
            "MEDIA_ROOT": "",
            "DB_PATH": "",
        },
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    # The guard's own logger writes to stdout by design (velo_log/settings.py's LOGGING
    # config), so the printed verdict is the last line, not the whole of stdout.
    assert result.stdout.strip().splitlines()[-1] == "inside_base_dir"
