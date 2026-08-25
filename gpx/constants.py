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
