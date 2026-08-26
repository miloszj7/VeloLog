# Logging Configuration — Plan Brief

> Full plan: `context/changes/logging-config/plan.md`

## What & Why

`velo_log/settings.py` has no `LOGGING` dict, so every log call in the app falls
through to Django's `lastResort` handler — bare messages to stderr, `extra` fields
silently dropped. This is Engineering Backlog item E-06, and its exact contract is
already documented as a comment in `settings.py`: a `velo_log` logger must stay
enabled, and the formatter must render the `media_root` extra `/healthz/` relies on
for diagnosing a misconfigured media path.

## Starting Point

`velo_log/urls.py`'s `/healthz/` view logs three failure conditions via
`logging.getLogger(__name__)` (`velo_log.urls`), two of them with
`extra={"media_root": ...}`. None of it is currently visible in a useful form —
`lastResort` prints the message only, with no timestamp, logger name, or extras.

## Desired End State

A `LOGGING` dict in `settings.py` routes all `velo_log.*` records to a formatted
stdout console handler (timestamp, level, logger, message, `media_root`), at
`INFO` when `DEBUG=True` and `WARNING` in production. Django's own framework
loggers (`django.request`, `django.server`) are left untouched.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| App log level | INFO (dev) / WARNING (prod), driven by `DEBUG` | Matches Django's own DEBUG-driven verbosity convention without a second env knob | Plan |
| Django framework loggers | Leave at Django defaults, no explicit entries | Avoids reintroducing request-log noise; Django already surfaces 500s by default | Plan |
| Formatter content | timestamp, level, logger name, message, `media_root` extra | Directly satisfies the settings.py comment's contract | Plan |
| Per-app loggers (accounts/trips/gpx) | None added now | No app currently logs anything — speculative config with nothing to verify against | Plan |
| Log destination | stdout only, no file handler | Matches container logging convention (`docker-linux.md`); Railway reads stdout | Plan |

## Scope

**In scope:**
- `LOGGING` dict in `velo_log/settings.py`
- Console handler + formatter rendering the `media_root` extra
- `velo_log` and root logger level split by `DEBUG`

**Out of scope:**
- File-based or structured/JSON logging
- Per-app logger entries (accounts, trips, gpx)
- An env-var-driven log level knob separate from `DEBUG`
- Any change to `django.*` framework logger config

## Architecture / Approach

One `LOGGING` dict, one `StreamHandler` to stdout, a formatter with a filter that
defaults a missing `media_root` field so records without the extra don't raise a
formatting error. `velo_log` logger set `propagate: False` to avoid double-emission
through root.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Add `LOGGING` config and verify | Working `LOGGING` dict + manual proof against both documented failure paths | Format string requiring `media_root` on every record could raise `KeyError` on log calls without the extra — mitigated with a default-filling filter |

**Prerequisites:** None — single-file change, no dependencies.
**Estimated effort:** ~1 short session, single phase.

## Open Risks & Assumptions

- Assumes no other in-flight change is about to add logging calls elsewhere that would
  need their own logger entries — none found in current codebase.

## Success Criteria (Summary)

- A misconfigured `MEDIA_ROOT` produces a fully formatted console line including
  `media_root=<path>`, where today it only prints a bare message.
- No duplicate log lines, no formatting errors on log calls without the extra.
