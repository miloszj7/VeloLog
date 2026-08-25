"""Named values for the GPX upload boundary."""

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
