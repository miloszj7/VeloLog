"""Named values for the GPX upload and render boundaries."""

# The upload ceiling enforced by `GpxUploadForm.clean_file`. It is a *validation* rule,
# not a resource bound: Django has already received the whole request body and spooled it
# to a temporary file before any clean method runs, and nothing upstream caps body size.
# See the plan's "What We're NOT Doing" — accepted explicitly for v1.
MAX_GPX_FILE_MEGABYTES = 10
MAX_GPX_FILE_BYTES = MAX_GPX_FILE_MEGABYTES * 1024 * 1024

# Compared case-insensitively against the user-supplied name. The extension is a
# convenience filter for the user, not a security control — `gpx/parsing.py` is what
# decides whether the bytes are usable.
ALLOWED_GPX_EXTENSIONS = (".gpx",)

# The ceiling on points in a single parsed track, enforced in `gpx/parsing.py`. Unlike the
# size cap this bounds the quantity that actually drives render cost: the `points` column is
# re-read and inlined into the trip detail page on every view. A 10 MB file of minimal
# `<trkpt>` elements parses to ~262,000 points and a 6 MB JSON payload — an upload that
# succeeds and then makes the page it belongs to unrenderable. Provisional: calibrated
# against that synthetic worst case (~24 bytes of JSON per point, so this caps the payload
# at ~2.4 MB), not yet against a real multi-day tour export.
MAX_GPX_POINTS = 100_000

# Decimal places kept for each stored coordinate. Five is roughly a metre — finer than a
# z19 tile can render — while gpxpy hands back full float precision, so a coordinate
# serialises as `50.061234567890123` and costs about twice the JSON bytes on a page that
# inlines every point. Rounded at the parse boundary so the stored column, the payload and
# every future consumer read the same value rather than re-deriving it.
COORDINATE_DECIMAL_PLACES = 5

# Paths of the Leaflet marker images `gpx/map_config.py` hands to the template, relative to
# a static root. Resolved through `static()` at render — never written out as literal URLs —
# because `CompressedManifestStaticFilesStorage` serves these under content-hashed names, so
# a hardcoded URL 404s in production while resolving fine under DEBUG. Leaflet's *default*
# icon builds these URLs at runtime, which the hashed manifest never rewrites; naming them
# here and passing them through the config is what keeps them off that path.
MARKER_ICON = "gpx/vendor/leaflet/images/marker-icon.png"
MARKER_ICON_RETINA = "gpx/vendor/leaflet/images/marker-icon-2x.png"
MARKER_SHADOW = "gpx/vendor/leaflet/images/marker-shadow.png"
