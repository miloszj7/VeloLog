# VeloLog

A trip-centric personal diary for multi-day cycling tours, aggregating GPX tracks and trip context into a single view.

**Production:** https://velolog-production.up.railway.app

## About

VeloLog is a course project built for [10xDevs](https://www.10xdevs.pl/) (3rd edition), an
intensive course teaching AI-native software engineering — building and maintaining real
projects with AI coding agents across the full development lifecycle, from a greenfield
build through quality gates, testing, and deployment.

## Development

See `AGENTS.md` for repository conventions and development commands.

## License

VeloLog is licensed under the [MIT License](LICENSE).

### Third-party licenses

VeloLog's own runtime dependencies (Django, django-environ, gunicorn, whitenoise) are
MIT/BSD-licensed. Two front-end libraries are vendored directly into this repository
rather than installed as packages:

| Library | Location | License |
|---|---|---|
| [Leaflet](https://leafletjs.com/) 1.9.4 | `gpx/static/gpx/vendor/leaflet/` | BSD-2-Clause |
| [Bootstrap](https://getbootstrap.com/) 5.3.8 | `static/vendor/bootstrap/` | MIT |

See each vendor directory's `README.md` for source, version, and upgrade notes.
`gpxpy`, a runtime dependency used to parse uploaded GPX files, is licensed under
Apache-2.0.
