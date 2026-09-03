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

# Unit conversions for the statistics derived at the parse boundary. gpxpy reports metres
# and seconds; kilometres, hours and minutes are display units and the conversion belongs
# in one named place rather than inline in a formatter.
METERS_PER_KILOMETER = 1000
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE

# The fewest points carrying an `<ele>` before `gpx/parsing.py` will report a climb.
# Two, because a climb is a sum of deltas and one point yields no delta: a file with a
# single elevated point satisfies every cheaper presence probe yet makes gpxpy return
# exactly the `(0, 0)` that would render as "0 m climbed" for an Alpine tour — the one
# string the elevation gate exists to prevent.
MIN_ELEVATED_POINTS = 2

# The minimum age a file under `MEDIA_ROOT` must have before `manage.py reconcile_media`
# will call it an orphan. This is the only thing separating a genuinely unreferenced file
# from one a request is in the middle of writing: `FileField.pre_save` commits the upload to
# storage *before* the INSERT it belongs to, so between those two moments the file is on
# disk and no row names it — indistinguishable from an orphan by set difference alone. The
# `/healthz/` probe writes and deletes its own file within one request for the same reason,
# so the threshold is also what makes walking `healthz/` safe rather than racy.
#
# An hour, sized against the real upper bound on a request rather than on the parse: gunicorn's
# default worker timeout is 30 s and the ~2 s parse is entirely upstream of the write, so this
# is roughly two orders of magnitude of headroom. Reclamation is human-triggered and rare, so
# the cost of being generous here is a file surviving one run — never a file deleted in flight.
ORPHAN_MIN_AGE_MINUTES = 60

# Paths of the Leaflet marker images `gpx/map_config.py` hands to the template, relative to
# a static root. Resolved through `static()` at render — never written out as literal URLs —
# because `CompressedManifestStaticFilesStorage` serves these under content-hashed names, so
# a hardcoded URL 404s in production while resolving fine under DEBUG. Leaflet's *default*
# icon builds these URLs at runtime, which the hashed manifest never rewrites; naming them
# here and passing them through the config is what keeps them off that path.
MARKER_ICON = "gpx/vendor/leaflet/images/marker-icon.png"
MARKER_ICON_RETINA = "gpx/vendor/leaflet/images/marker-icon-2x.png"
MARKER_SHADOW = "gpx/vendor/leaflet/images/marker-shadow.png"

# Project-authored pin SVGs, one per marker kind, replacing the shared default pin above
# for the "start" / "finish" / "break" entries in `gpx/map_config.py`'s `icons` map — the
# PRD's "distinct markers, without hovering" acceptance criterion (`prd.md:96-97,127`).
# Text assets, not vendored: no third-party licence to clear and no `SHA256SUMS` entry.
# One file serves both pixel densities (`iconRetinaUrl` points at the same path as
# `iconUrl`), and the vendored PNG shadow above is still used for all three.
MARKER_STAGE_START = "gpx/markers/stage-start.svg"
MARKER_STAGE_FINISH = "gpx/markers/stage-finish.svg"
MARKER_STAGE_BREAK = "gpx/markers/stage-break.svg"

# Hues cycled across a trip's stages when drawing its route, keyed by stage index — stage 7
# reuses stage 1's colour. The design system (`design-system.md` "Stage Route Palette")
# forbids additional colours everywhere except this one bounded exception: map polylines and
# their stage-list swatches, never interface chrome. The first entry is deliberately the
# system's own accent (`--color-accent: #f97316`), so a single-stage trip draws in the colour
# the system already specifies — and this is also where the pre-existing `#ff7800` drift in
# `gpx/static/gpx/map.js` gets reconciled to that accent. The rest are chosen to stay
# distinguishable from each other and legible over the OpenStreetMap basemap.
STAGE_COLORS: tuple[str, ...] = (
    "#f97316",  # accent orange — stage 1, matches the design system exactly
    "#2563eb",  # blue
    "#16a34a",  # green
    "#dc2626",  # red
    "#9333ea",  # purple
    "#0891b2",  # teal
)
