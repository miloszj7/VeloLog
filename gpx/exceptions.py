"""Exception hierarchy for the gpx app.

The parsing layer raises these rather than letting `gpxpy`'s own exception types reach
the form, so the form catches one project-owned type instead of a third-party one.
"""


class GpxError(Exception):
    """Base exception for every failure originating in the gpx app."""


class GpxParseError(GpxError):
    """Raised when an uploaded document cannot be turned into a usable track."""


class GpxSyntaxError(GpxParseError):
    """The document is not well-formed XML, or is not safe to hand to a parser at all."""


class GpxContentError(GpxParseError):
    """The document is well-formed XML but is not a usable GPX track."""
