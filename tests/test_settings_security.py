"""Assert the production security block in `velo_log/settings.py` when DEBUG is false.

The autouse `_disable_ssl_redirect` fixture in `conftest.py` neutralizes
`SECURE_SSL_REDIRECT` for every other test, which hides the `if not DEBUG:` block
from any test that exercises it through the Django test client. This test asserts
the block's configuration directly instead.
"""

import importlib
import os
from unittest import mock

import velo_log.settings


def test_production_security_settings_enabled_when_debug_false() -> None:
    try:
        with mock.patch.dict(os.environ, {"DEBUG": "False"}):
            importlib.reload(velo_log.settings)
            assert velo_log.settings.SECURE_SSL_REDIRECT is True
            assert velo_log.settings.SESSION_COOKIE_SECURE is True
            assert velo_log.settings.CSRF_COOKIE_SECURE is True
            assert velo_log.settings.SECURE_PROXY_SSL_HEADER == (
                "HTTP_X_FORWARDED_PROTO",
                "https",
            )
            assert velo_log.settings.SECURE_HSTS_SECONDS > 0
    finally:
        # Reload outside the patched environment so the mutated sys.modules entry
        # does not leak DEBUG=False into later tests.
        importlib.reload(velo_log.settings)
