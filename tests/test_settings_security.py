"""Assert the production security block in `velo_log/settings.py` when DEBUG is false.

The autouse `_disable_ssl_redirect` fixture in `conftest.py` neutralizes
`SECURE_SSL_REDIRECT` for every other test, which hides the `if not DEBUG:` block
from any test that exercises it through the Django test client. This test asserts
the block's configuration directly instead.

The module under test is loaded fresh via `spec_from_file_location` into a throwaway
module object that is never registered in `sys.modules`, rather than
`importlib.reload`-ing `velo_log.settings` in place — reloading re-executes into the
existing module namespace without clearing it first, so settings the `if not DEBUG:`
block sets would survive into the reloaded (DEBUG=True) module and leak into any test
that later inspects `velo_log.settings` directly.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "velo_log" / "settings.py"


def _load_settings() -> ModuleType:
    spec = importlib.util.spec_from_file_location("velo_log_settings_probe", SETTINGS_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_production_security_settings_enabled_when_debug_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBUG", "False")
    settings = _load_settings()
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.SECURE_PROXY_SSL_HEADER == (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )
    assert settings.SECURE_HSTS_SECONDS > 0
