"""Assert the security configuration in `velo_log/settings.py`.

Two kinds of setting live here. The first is the production block: the autouse
`_disable_ssl_redirect` fixture in `conftest.py` neutralizes `SECURE_SSL_REDIRECT`
for every other test, which hides the `if not DEBUG:` block from any test that
exercises it through the Django test client, so this module asserts the block's
configuration directly instead. The second is `SECURE_REFERRER_POLICY`, which sits at
module level precisely so it is *not* production-only, and is therefore asserted under
both `DEBUG` values rather than just the one.

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

from tests.conftest import OSM_BLOCKING_REFERRER_POLICIES, OSM_COMPLIANT_REFERRER_POLICIES

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


@pytest.mark.parametrize("debug", ["True", "False"])
def test_referrer_policy_is_osm_compliant_in_both_debug_modes(
    monkeypatch: pytest.MonkeyPatch,
    debug: str,
) -> None:
    """Pin `SECURE_REFERRER_POLICY` to a value OpenStreetMap's tile usage policy accepts.

    Asserted under both `DEBUG` values because the setting is module-level rather than part
    of the `if not DEBUG:` block. A `DEBUG=False`-only assertion would stay green if the
    line were moved inside that block, which would leave development sending Django's
    `same-origin` default — and the trip map's tiles are fetched from OpenStreetMap the same
    way in both modes, so that move would make the resulting 403 block unobservable
    anywhere but production. That is how it shipped unnoticed the first time.

    None of the three assertions is redundant. The first reads the setting through
    `getattr` so that deleting the line — the likeliest regression, since a non-default
    security setting invites being "cleaned up" — fails naming the consequence rather than
    raising a bare `AttributeError`; an absent setting is not a neutral state, it is
    Django's blocking `same-origin` default. The second fails if the value drifts to
    anything outside the compliant set. The third still fails if someone widens
    `OSM_COMPLIANT_REFERRER_POLICIES` itself to readmit one of the two values OpenStreetMap
    names as blocking.
    """
    monkeypatch.setenv("DEBUG", debug)
    settings = _load_settings()

    policy = getattr(settings, "SECURE_REFERRER_POLICY", None)
    assert policy is not None, (
        "`SECURE_REFERRER_POLICY` is unset, so Django's `same-origin` default applies and "
        "OpenStreetMap blocks every tile on the trip detail page"
    )
    assert policy in OSM_COMPLIANT_REFERRER_POLICIES
    assert policy not in OSM_BLOCKING_REFERRER_POLICIES
