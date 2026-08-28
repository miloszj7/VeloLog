"""Prove the logging context filter defaults every optional key without overwriting one.

The `verbose` formatter names `media_root`, `track_id` and `storage_key` unconditionally,
so a record that supplies none of them must still format. That is the filter's whole job,
and the reason it exists is a real failure mode: a missing key raises `KeyError` at format
time, which means the *log line* fails on the path where something already went wrong.

The non-overwrite half is what makes the widening worth anything. `gpx/signals.py` passes
`track_id` and `storage_key` on the one line that reports a file it could not remove; a
filter that clobbered them would render the line and still not name the key an operator
has to feed to `reconcile_media`.

`velo_log/settings.py` is omitted from coverage (`pyproject.toml`), so these tests are for
correctness, not for the gate.
"""

import logging
from typing import Any, cast

from velo_log.settings import LOG_CONTEXT_KEYS, _LogContextDefaultFilter

VERBOSE_FORMAT = (
    "{asctime} {levelname} {name} {message} "
    "media_root={media_root} track_id={track_id} storage_key={storage_key}"
)


def _bare_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="gpx.signals",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Could not delete a superseded or deleted track's file",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_filter_defaults_every_context_key_to_empty() -> None:
    record = _bare_record()

    assert _LogContextDefaultFilter().filter(record) is True
    for key in LOG_CONTEXT_KEYS:
        assert record.__dict__[key] == ""


def test_filter_does_not_overwrite_a_key_the_caller_supplied() -> None:
    """The assertion the widening exists to make — the key must survive to the line."""
    record = _bare_record(track_id=7, storage_key="gpx/1/2/deadbeef.gpx")

    assert _LogContextDefaultFilter().filter(record) is True
    # `record.__dict__`, not attribute access: `LogRecord` declares none of these
    # statically, which is the whole reason the filter has to inject them.
    assert record.__dict__["track_id"] == 7
    assert record.__dict__["storage_key"] == "gpx/1/2/deadbeef.gpx"
    assert record.__dict__["media_root"] == ""


def test_verbose_format_renders_a_record_with_no_context() -> None:
    """The `KeyError` this filter prevents is raised by the formatter, not by the filter."""
    record = _bare_record()
    _LogContextDefaultFilter().filter(record)

    line = logging.Formatter(VERBOSE_FORMAT, style="{").format(record)

    assert "media_root= track_id= storage_key=" in line


def test_verbose_format_names_the_stranded_key() -> None:
    record = _bare_record(track_id=7, storage_key="gpx/1/2/deadbeef.gpx")
    _LogContextDefaultFilter().filter(record)

    line = logging.Formatter(VERBOSE_FORMAT, style="{").format(record)

    assert "track_id=7 storage_key=gpx/1/2/deadbeef.gpx" in line


def test_every_key_the_verbose_format_names_is_defaulted() -> None:
    """A key added to the format string but not to `LOG_CONTEXT_KEYS` is the regression."""
    for key in LOG_CONTEXT_KEYS:
        assert "{" + key + "}" in VERBOSE_FORMAT

    from velo_log.settings import LOGGING

    formatters = cast(dict[str, dict[str, Any]], LOGGING["formatters"])
    assert formatters["verbose"]["format"] == VERBOSE_FORMAT
