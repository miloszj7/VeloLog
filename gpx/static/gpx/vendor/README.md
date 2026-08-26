# Vendored front-end assets

## `leaflet/` — Leaflet 1.9.4

- **Version**: 1.9.4 (released 2023-05-18; still the current stable release — 2.0 has been
  alpha since 2025-05 with its release date reset to "unknown").
- **Source**: <https://unpkg.com/leaflet@1.9.4/dist/> — the `dist/` directory of the
  `leaflet@1.9.4` npm package.
- **Licence**: BSD-2-Clause (see the banner at the top of `leaflet.js`).
- **Vendored, not CDN-loaded**, so the app has no third-party runtime dependency for its
  own code and no SRI convention to invent.

### What is here, and why each file has to be

`CompressedManifestStaticFilesStorage` rewrites every reference a collected CSS/JS file
makes to a sibling file, and raises `MissingFileError` on any it cannot resolve. Because
`railway.json` `&&`-chains `collectstatic` ahead of `gunicorn`, that error is a boot
outage, not a degraded deploy. So: **every reference a vendored asset makes to a sibling
must be vendored alongside it.**

| File | Why it is required |
|---|---|
| `leaflet.js` | The library. |
| `leaflet.js.map` | `leaflet.js` ends with `//# sourceMappingURL=leaflet.js.map`, which Django resolves like any other reference. Vendored rather than stripped so the bytes stay identical to upstream and an upgrade is a straight file swap. |
| `leaflet.css` | The library's stylesheet. |
| `images/layers.png`, `images/layers-2x.png`, `images/marker-icon.png` | Referenced by `url(...)` from `leaflet.css`. |
| `images/marker-icon-2x.png`, `images/marker-shadow.png` | Not referenced from the CSS — `gpx/map.js` passes them to `L.icon` explicitly. Leaflet's *default* icon builds these URLs at runtime, which the hashed manifest never rewrites; passing them from the template through `{% static %}` is what keeps them off that path. |

If `collectstatic` ever fails with `MissingFileError`, the fix is to vendor the missing
sibling. Relaxing `WHITENOISE_MANIFEST_STRICT` or downgrading the storage class would
trade a loud build failure for silently broken asset URLs in production.

### Upgrading

Replace the whole `leaflet/` directory with a new release's `dist/` files, update the
version above, and run `uv run python manage.py collectstatic --noinput` — the CI `gates`
job runs the same command, so an unvendored new sibling fails the PR rather than the deploy.

Then regenerate the checksums, or the integrity gate below fails the PR for the upgrade
itself:

```bash
cd gpx/static/gpx/vendor
sha256sum leaflet/leaflet.js leaflet/leaflet.js.map leaflet/leaflet.css leaflet/images/*.png > SHA256SUMS
```

Regenerating is the *last* step of an upgrade, after the new bytes have been checked
against the upstream release — a blind regenerate turns the gate back into a record of
whatever happens to be on disk.

### SHA-256 of the vendored bytes

These are a *control*, not a note. The same digests live in `SHA256SUMS` beside this file,
and `.github/workflows/deploy.yml` runs `sha256sum -c SHA256SUMS` as the first `gates`
step, so a tampered, truncated or line-ending-mangled asset fails the pull request.
Nothing downstream would otherwise notice: `collectstatic` content-hashes whatever bytes
it finds, so a corrupted file deploys under a valid-looking hashed name.

The table is reproduced here for readability; `SHA256SUMS` is what runs. Keep them in step
— the two are generated from the same command in *Upgrading* above.

```
db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a *leaflet/leaflet.js
600a10dc5cd110de0699510d322afcbe01c7ca90b4c5f48adc20314c70aac753 *leaflet/leaflet.js.map
a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6 *leaflet/leaflet.css
1dbbe9d028e292f36fcba8f8b3a28d5e8932754fc2215b9ac69e4cdecf5107c6 *leaflet/images/layers.png
066daca850d8ffbef007af00b06eac0015728dee279c51f3cb6c716df7c42edf *leaflet/images/layers-2x.png
574c3a5cca85f4114085b6841596d62f00d7c892c7b03f28cbfa301deb1dc437 *leaflet/images/marker-icon.png
00179c4c1ee830d3a108412ae0d294f55776cfeb085c60129a39aa6fc4ae2528 *leaflet/images/marker-icon-2x.png
264f5c640339f042dd729062cfc04c17f8ea0f29882b538e3848ed8f10edb4da *leaflet/images/marker-shadow.png
```
