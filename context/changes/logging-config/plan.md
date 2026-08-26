# Logging Configuration Implementation Plan

## Overview

`velo_log/settings.py` currently has no `LOGGING` dict. Every log call in the codebase
(most notably `/healthz/`'s `logger.exception` / `logger.error` calls in
`velo_log/urls.py`) falls through to Django's `logging.lastResort` handler, which prints
only the bare message to stderr with no timestamp, no logger name, and — critically —
drops any `extra={}` payload entirely. This is Engineering Backlog item **E-06**.

This plan adds a `LOGGING` dict that resolves the two obligations the settings.py
comment (lines 190-202) already documents:

1. A `velo_log` logger must exist and stay enabled, or `/healthz/`'s only diagnostic
   channel for the store-unreachable case disappears.
2. The formatter must render the `media_root` extra, or the misconfigured-path detail
   `_media_root_context()` deliberately withholds from the anonymous caller stays
   invisible server-side too.

## Current State Analysis

- `velo_log/settings.py:187-202` — the `# Logging` section is a placeholder comment
  only; no `LOGGING` dict exists.
- `velo_log/urls.py:70-153` — `_database_round_trips`, `media_root_misconfiguration`,
  and `_media_round_trips` all log via `logger = logging.getLogger(__name__)`
  (`__name__` here is `velo_log.urls`, a child of `velo_log`). Two calls pass
  `extra=_media_root_context()` (a `{"media_root": ...}` dict); the rest use
  `logger.exception` with no extra.
- `gpx/views.py:18` also calls `logging.getLogger(__name__)` (`gpx.views` — **not** a
  descendant of `velo_log`). Two call sites there (`:44`, `:172`) use
  `logger.exception(..., extra={"track_id": ..., "storage_key": ...})`. Because
  `gpx.views` isn't under the `velo_log` logger name, only the root (`""`) logger
  reaches it — the root handler this plan adds is therefore load-bearing for an
  existing call site today, not just future-proofing for hypothetical app loggers.
- `accounts/` and `trips/` do not call `logging.getLogger` anywhere. `velo_log.urls`
  and `gpx.views` are the only two call sites in the codebase today.
- No `config/logging.yaml` or `config/` directory exists in this repo — the Django
  convention (a `LOGGING` dict inline in `settings.py`) is what the placeholder comment
  already anticipates, and is what this plan follows.
- Per `docker-linux.md`, containerized processes log to stdout/stderr; Railway's log
  aggregation reads that stream. No handler in this plan writes to a file.

## Desired End State

`velo_log/settings.py` defines a `LOGGING` dict such that:

- Any log record from `velo_log.*` loggers (including `velo_log.urls`) reaches stdout
  via a console handler, formatted with timestamp, level, logger name, message, and any
  `extra` fields (specifically `media_root`).
- The root/`velo_log` logger threshold is `INFO` when `DEBUG=True`, `WARNING` when
  `DEBUG=False`.
- `django.*` loggers (e.g. `django.request`, `django.server`) are left unconfigured in
  `LOGGING["loggers"]` and inherit Django's own default logging config for those names,
  per Django's disable_existing_loggers/incremental merge behavior.
- `disable_existing_loggers` is `False`.

**Verification:** trigger `/healthz/` locally with `MEDIA_ROOT` set to a relative path
(or a path inside `BASE_DIR`) and confirm the resulting console output includes the
timestamp, `velo_log.urls`, the log message, and `media_root=<value>` — where today it
would print only the bare message via `lastResort`.

### Key Discoveries:

- `velo_log/urls.py:114` and `:117-120` — the two `extra=_media_root_context()` call
  sites this formatter must render.
- `velo_log/settings.py:187-202` — the full contract this plan must satisfy, written in
  by a prior change specifically so E-06 wouldn't need to rediscover it.
- Django's `LOGGING` merges with its own default config by logger name — configuring
  only `""` (root) and `velo_log` does not remove Django's own `django`/`django.server`
  handlers, so `/healthz/`'s existing framework-level error visibility (500s) is
  unaffected by this change.

## What We're NOT Doing

- No file-based log handler (violates the stdout-only container convention; no volume
  is reserved for logs).
- No structured/JSON log formatting (no log aggregator exists yet; plain text is
  readable in Railway's log viewer and local `runserver` output).
- No explicit `LOGGING["loggers"]` entries for `django.request` / `django.server` — left
  at Django's defaults.
- No per-app (`accounts`, `trips`, `gpx`) logger entries — `gpx.views` reaches the
  console handler via root propagation instead (see Current State Analysis); `accounts`
  and `trips` have no call sites at all. Adding dedicated entries now would be
  speculative config beyond what the two real call sites need.
- No expansion of the formatter's rendered fields beyond `media_root` — `gpx/views.py`'s
  `extra={"track_id": ..., "storage_key": ...}` will reach the console handler and be
  filtered/leveled correctly, but `track_id`/`storage_key` won't render in the line
  (Python's formatter only renders `extra` keys explicitly named in the format string).
  The settings.py comment this plan closes out only mandates rendering `media_root`;
  widening the formatter for gpx's fields is a separate, later decision.
- No log level configurable via environment variable — `DEBUG` already drives the
  split, and introducing a second knob is unwarranted for a single-developer project.

## Implementation Approach

Single-file change to `velo_log/settings.py`, inserted into the existing `# Logging`
section, replacing the placeholder comment. The comment's two hard constraints
(velo_log logger enabled, media_root-rendering formatter) become the `LOGGING` dict's
acceptance criteria.

## Phase 1: Add `LOGGING` configuration and verify

### Overview

Write the `LOGGING` dict into `velo_log/settings.py`, then manually verify both
documented failure paths (misconfigured `MEDIA_ROOT`, media round-trip failure) now
surface fully formatted output including the `media_root` extra.

### Changes Required:

#### 1. `LOGGING` dict

**File**: `velo_log/settings.py`

**Intent**: Replace the placeholder `# Logging` comment block (lines 187-202) with a
working `LOGGING` dict, keeping the two constraint bullets as inline comments
explaining *why* those two pieces exist (so a future reader doesn't strip them as
dead config).

**Contract**: Django `LOGGING` dict, `version: 1`, `disable_existing_loggers: False`.
One formatter (`verbose`) with a `format` string rendering `asctime`, `levelname`,
`name`, `message`, plus the extras this project's log calls actually use — Django's
formatter renders arbitrary `extra` keys only if they're named in the format string, so
`media_root` must appear explicitly:

```python
"format": "{asctime} {levelname} {name} {message} media_root={media_root}",
"style": "{",
```

Accepted tradeoff: this appends a `media_root=` field to every line through this
handler, including calls unrelated to media (e.g. `gpx.views`' `track_id`/
`storage_key` calls), usually rendering as an empty trailing field. Fine at the
current 2-call-site scale; revisit if the formatter needs to grow beyond a single
project-wide `extra` field.

This means every log record funneled through this formatter must carry a
`media_root` field or `str.format` raises `KeyError` at format time. Since call sites
log through this handler with the extra sometimes present and sometimes absent
(`logger.exception` calls with no `extra=`), use a `logging.Filter` (not a bare format
string) to inject a default `media_root=""` onto any record missing the key, then have
the formatter reference `{media_root}` unconditionally. Define the filter directly in
`velo_log/settings.py`, immediately above the `LOGGING` dict:

```python
class _MediaRootDefaultFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "media_root"):
            record.media_root = ""
        return True
```

Wire it via `LOGGING["filters"]`, referencing the class by dotted path (dictConfig's
`"()"` key instantiates a callable):

```python
"filters": {
    "media_root_default": {"()": "velo_log.settings._MediaRootDefaultFilter"},
},
```

Register the filter on the handler via its `"filters"` list.

One handler, named `velo_log_console` — **not** `console`: Django's own
`DEFAULT_LOGGING` already registers a handler literally named `console` (gated by a
`require_debug_true` filter, wired to the `django` logger). Because the project's
`LOGGING` dict is applied via a second `dictConfig` call on top of Django's own,
reusing the name `console` would reconfigure that *same* handler object in place —
silently dropping its `require_debug_true` filter and swapping in this formatter,
even though `django.*` loggers are meant to be left untouched (see below). Use
`logging.StreamHandler`, `stream: ext://sys.stdout`, `formatter: verbose`,
`filters: ["media_root_default"]`.

Two logger entries:
- `""` (root): `handlers: ["velo_log_console"]`, `level: "INFO" if DEBUG else "WARNING"`.
- `"velo_log"`: `handlers: ["velo_log_console"]`, `level: "INFO" if DEBUG else "WARNING"`,
  `propagate: False` (prevents double-emission through root, since `velo_log.urls` is a
  child of `velo_log`, which is itself unrelated to root by name but Django's default
  root-propagation would otherwise duplicate every record onto both the `velo_log` and
  `""` handlers).

Do not add `django` / `django.request` / `django.server` entries — leave them absent so
Django's own default logging config for those names applies unchanged.

**Known tradeoff — Django's `"django"` logger double-prints.** Django's own
`"django"` logger does not set `propagate: False` in `DEFAULT_LOGGING` (only
`"django.server"` does), so once the root logger has a handler attached, any record
already handled by Django's own `console`/`mail_admins` handlers *also* reaches root
and prints a second time, in this plan's format instead of Django's. This is accepted
rather than engineered around: this is a low-traffic personal project, the duplication
is confined to `DEBUG=True` local dev (Django's own `console` handler is gated by
`require_debug_true`), and avoiding it would mean either giving `"django"` an explicit
`propagate: False` (which risks suppressing a framework message this plan has no
mandate to touch) or dropping the root handler (which would break `gpx.views`'
coverage — see Current State Analysis). Phase 1's manual verification confirms the
duplication is limited to this known case and doesn't hide anything else.

### Success Criteria:

#### Automated Verification:

- `manage.py check` passes: `uv run python manage.py check`
- Full quality gates pass: `/python-quality-gates`
- Existing test suite passes unaffected: `uv run pytest --cov`

#### Manual Verification:

- Run `uv run python manage.py runserver` locally with `MEDIA_ROOT` temporarily set to
  a relative path (or unset, which resolves inside `BASE_DIR`) and hit `/healthz/`;
  confirm the console shows a fully formatted line (timestamp, `ERROR`, `velo_log.urls`,
  the message, and `media_root=<path>`) rather than a bare message.
- Restore `MEDIA_ROOT` to its normal value, confirm `/healthz/` returns 200 and no
  spurious error-level output appears in the console for a healthy request.
- Confirm no duplicate log lines appear (verifying `propagate: False` on `velo_log`
  actually prevents the double-emission it's meant to prevent).
- Trigger a Django framework log line (e.g. a dev-server request at `DEBUG=True`) and
  confirm the only duplication observed is the known `"django"`-logger-vs-root case
  documented above — not some other unexpected double-emission.
- Trigger `gpx/views.py:44` or `:172` locally (delete a track's underlying file on disk,
  then request its download or trigger a supersede) and confirm the resulting console
  line is fully formatted (timestamp, level, `gpx.views`, message) via root propagation
  — proving the root handler covers this real call site, not just `velo_log.urls`.

**Implementation Note**: After completing this phase and all automated verification
passes, pause here for manual confirmation from the human that the manual testing was
successful before proceeding.

---

## Testing Strategy

### Unit Tests:

- No new unit tests are required — `LOGGING` is infrastructure config, not application
  logic with a testable contract of its own. Existing tests already exercise the
  `/healthz/` code paths that emit these log records; those tests assert response
  bodies/status codes, not log output, and continue to do so.

### Manual Testing Steps:

1. Temporarily misconfigure `MEDIA_ROOT` (relative path), hit `/healthz/`, confirm the
   console log line is fully formatted with `media_root` visible.
2. Restore `MEDIA_ROOT`, confirm a healthy `/healthz/` call produces no error-level
   output.
3. Confirm no duplicate lines (root vs `velo_log` propagation).

## Performance Considerations

None — a `StreamHandler` to stdout on a low-traffic personal project has no measurable
overhead.

## Migration Notes

Not applicable — no data model or schema change.

## References

- Related backlog item: `context/foundation/roadmap.md` → Engineering Backlog → E-06
- Constraint source: `velo_log/settings.py:187-202`
- Call sites this must satisfy: `velo_log/urls.py:70-153`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Add `LOGGING` configuration and verify

#### Automated

- [x] 1.1 `manage.py check` passes — 98aa62e
- [x] 1.2 Full quality gates pass — 98aa62e
- [x] 1.3 Existing test suite passes unaffected — 98aa62e

#### Manual

- [x] 1.4 Misconfigured `MEDIA_ROOT` produces fully formatted console output with `media_root` visible — 98aa62e
- [x] 1.5 Healthy `/healthz/` call produces no spurious error-level output — 98aa62e
- [x] 1.6 No duplicate log lines from root/`velo_log` propagation — 98aa62e
- [x] 1.7 `gpx/views.py` log call surfaces correctly via root propagation — 98aa62e
- [x] 1.8 Django framework log line's duplication is limited to the documented known case — 98aa62e
