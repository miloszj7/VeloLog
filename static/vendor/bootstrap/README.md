# Vendored front-end assets

## `bootstrap/` — Bootstrap 5.3.8

- **Version**: 5.3.8 (released 2025; the current stable Bootstrap 5 release).
- **Source**: <https://unpkg.com/bootstrap@5.3.8/dist/> — the `dist/` directory of the
  `bootstrap@5.3.8` npm package.
- **Licence**: MIT (see the banner at the top of `bootstrap.min.css` and
  `bootstrap.bundle.min.js`).
- **Vendored, not CDN-loaded**, so the app has no third-party runtime dependency for its
  own code and no SRI convention to invent — matching the posture already established for
  Leaflet in `gpx/static/gpx/vendor/`.

### What is here, and why each file has to be

`CompressedManifestStaticFilesStorage` rewrites every reference a collected CSS/JS file
makes to a sibling file, and raises `MissingFileError` on any it cannot resolve. Because
`railway.json` `&&`-chains `collectstatic` ahead of `gunicorn`, that error is a boot
outage, not a degraded deploy. So: **every reference a vendored asset makes to a sibling
must be vendored alongside it.**

| File | Why it is required |
|---|---|
| `bootstrap.min.css` | The compiled stylesheet. |
| `bootstrap.min.css.map` | `bootstrap.min.css` ends with `/*# sourceMappingURL=bootstrap.min.css.map */`, which Django resolves like any other reference. Vendored rather than stripped so the bytes stay identical to upstream and an upgrade is a straight file swap. |
| `bootstrap.bundle.min.js` | The library's JS, bundled with Popper so `dropdown`/`tooltip`/`popover` components work without a separate Popper vendor entry. |
| `bootstrap.bundle.min.js.map` | `bootstrap.bundle.min.js` ends with `//# sourceMappingURL=bootstrap.bundle.min.js.map`, resolved the same way. |

If `collectstatic` ever fails with `MissingFileError`, the fix is to vendor the missing
sibling. Relaxing `WHITENOISE_MANIFEST_STRICT` or downgrading the storage class would
trade a loud build failure for silently broken asset URLs in production.

### Upgrading

Replace the four files above with a new release's `dist/` files, update the version
above, and run `uv run python manage.py collectstatic --noinput` — the CI `gates` job
runs the same command, so an unvendored new sibling fails the PR rather than the deploy.

Then regenerate the checksums, or the integrity gate below fails the PR for the upgrade
itself:

```bash
cd static/vendor/bootstrap
sha256sum *.css *.css.map *.js *.js.map > SHA256SUMS
```

Regenerating is the *last* step of an upgrade, after the new bytes have been checked
against the upstream release — a blind regenerate turns the gate back into a record of
whatever happens to be on disk.

### SHA-256 of the vendored bytes

These are a *control*, not a note. The same digests live in `SHA256SUMS` beside this file,
and `.github/workflows/deploy.yml` runs `sha256sum -c SHA256SUMS` (in a step distinct from
the Leaflet one) as an early `gates` step, so a tampered, truncated or line-ending-mangled
asset fails the pull request. Nothing downstream would otherwise notice: `collectstatic`
content-hashes whatever bytes it finds, so a corrupted file deploys under a valid-looking
hashed name.

The table is reproduced here for readability; `SHA256SUMS` is what runs. Keep them in step
— the two are generated from the same command in *Upgrading* above.

```
d85327d99c7a3ee1f9b5d0500d1370acea3ad2db39c163c2f51f232baedbdede *bootstrap.min.css
48144faf6aa0fb3cd2ce748d9730238f888f4ab715f05dabd1c9af2c5671988a *bootstrap.min.css.map
e4fd49181388c48ec5040bd3fe66f57c29c8e67fcd8502b3354b96ec7ab47cc7 *bootstrap.bundle.min.js
c61123e58cc0a4b65d737ba070c485911b3dbec6d7b802bdf6628395abd9c08b *bootstrap.bundle.min.js.map
```
