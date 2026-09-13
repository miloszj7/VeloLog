"""Pin the tile layer's `referrerPolicy` in the shipped `gpx/static/gpx/map.js`.

This is a source-text pin, not a behavioural proof. It asserts the option is written into
the file with a value OpenStreetMap accepts, and says nothing about whether Leaflet honours
it at runtime — a Leaflet upgrade that stopped reading the option would leave this green.
That limit is deliberate rather than an oversight: there is no JS test runner in this repo,
and `tests/e2e/` is not wired into `.github/workflows/deploy.yml`, so reading the shipped
asset is the only guard available inside a gate CI actually runs.

What it does catch is the failure that matters here — the option being dropped in a later
edit. Its counterpart in `tests/test_settings_security.py` pins the global response header,
and either alone is enough to keep tiles loading today; this one exists because the global
header is the half a privacy pass would plausibly tighten back to `same-origin`, at which
point the layer option is the only thing left standing between a rider and a map full of
403 placeholders.

The tile URL is pinned alongside the option because a pin on the option alone goes vacuous
if the provider ever changes: it is OpenStreetMap's policy that makes `referrerPolicy`
load-bearing, so the assertion should stop applying loudly rather than silently.
"""

import re
from pathlib import Path

from tests.conftest import OSM_COMPLIANT_REFERRER_POLICIES

MAP_JS = Path(__file__).resolve().parents[2] / "gpx" / "static" / "gpx" / "map.js"

# The `L.tileLayer(url, {...})` call and its options object. `[^}]*` suffices for the
# options because they are flat — no nested object literal appears between the braces — and
# it stops the match at the call's own closing brace rather than running to the end of the
# file. The URL is captured from its own quoted literal, so the `{z}/{x}/{y}` placeholders
# inside it cannot be mistaken for that brace.
TILE_LAYER_CALL = re.compile(
    r"""L\.tileLayer\(\s*["'](?P<url>[^"']+)["']\s*,\s*\{(?P<options>[^}]*)\}""",
    re.DOTALL,
)
REFERRER_POLICY_OPTION = re.compile(r"""referrerPolicy:\s*["'](?P<value>[^"']+)["']""")


def test_tile_layer_sends_an_osm_compliant_referrer_policy() -> None:
    """Assert `map.js` builds its tile layer with a `referrerPolicy` OpenStreetMap accepts.

    Searches the options object of the `L.tileLayer` call specifically, not the file as a
    whole, so the option named in this file's own header comment cannot satisfy the
    assertion in place of the real one.
    """
    source = MAP_JS.read_text(encoding="utf-8")

    call = TILE_LAYER_CALL.search(source)
    assert call is not None, f"no `L.tileLayer(url, {{...}})` call found in {MAP_JS}"
    assert "tile.openstreetmap.org" in call.group("url"), (
        f"tile provider is no longer OpenStreetMap ({call.group('url')!r}) — this pin "
        f"exists to satisfy OpenStreetMap's tile usage policy, so revisit whether it "
        f"still applies rather than deleting it"
    )

    option = REFERRER_POLICY_OPTION.search(call.group("options"))
    assert option is not None, (
        "the `L.tileLayer` options carry no `referrerPolicy`, so tiles inherit the page's "
        "global `Referrer-Policy` — OpenStreetMap blocks tile requests that arrive with no "
        "`Referer`"
    )
    assert option.group("value") in OSM_COMPLIANT_REFERRER_POLICIES
