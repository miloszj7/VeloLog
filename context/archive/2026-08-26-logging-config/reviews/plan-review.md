<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Logging Configuration Implementation Plan

- **Plan**: context/changes/logging-config/plan.md
- **Mode**: Deep
- **Date**: 2026-08-26
- **Verdict**: RETHINK
- **Findings**: 2 critical, 2 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | WARNING |
| Architectural Fitness | FAIL |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

3/3 paths ✓ (`velo_log/settings.py`, `velo_log/urls.py`, `context/changes/logging-config/`), symbols ✓ (`media_root_misconfiguration`, `_media_root_context`, `HEALTHZ_MEDIA_KEY`), brief↔plan ✓.

Sub-agent blast-radius sweep: confirmed no other `LOGGING` dict or `console` handler exists anywhere in this repo — the naming-collision finding below is against **Django's own internal default config**, not anything local. Also found a second `logging.getLogger` call site the plan's Current State Analysis missed: `gpx/views.py:18`.

## Findings

### F1 — Handler name `"console"` collides with Django's own DEFAULT_LOGGING handler

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Architectural Fitness
- **Location**: Phase 1 — Changes Required §1, Contract
- **Detail**: Verified against Django 6.0's official docs (`DEFAULT_LOGGING` in `django/utils/log.py`): Django already registers a handler named `"console"` (a `StreamHandler` gated by the `require_debug_true` filter) and wires it to the `"django"` logger. `configure_logging()` applies `DEFAULT_LOGGING` via `dictConfig` first, then applies the project's `LOGGING` via a second `dictConfig` call. Per Python's `dictConfig` semantics, a handler defined under the same name in the second call **reconfigures the existing handler object in place** — and since the `"django"` logger already holds a reference to that same object, it silently starts emitting through the project's formatter with the `require_debug_true` filter dropped (the plan's handler def doesn't include it). That's a production behavior change (django-level INFO+ messages start reaching console in prod, where Django's own default explicitly suppresses them) even though the plan's stated intent is to leave `django.*` loggers untouched.
- **Fix**: Rename the handler key to something outside Django's reserved names (e.g. `"velo_log_console"`) and reference that name from the `""` and `"velo_log"` logger entries. Do not reuse `"console"`.
- **Decision**: FIXED

### F2 — Current State Analysis is factually wrong: `gpx/views.py` already logs

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Current State Analysis; "What We're NOT Doing"
- **Detail**: The plan states "No other app (`accounts/`, `trips/`, `gpx/`) currently calls `logging.getLogger` anywhere — `velo_log.urls` is the only call site in the codebase today," and uses that premise to justify "No per-app (`accounts`, `trips`, `gpx`) logger entries." A sub-agent grep confirms `gpx/views.py:18` also has `logger = logging.getLogger(__name__)` (logger name `gpx.views`). Because `gpx.views` is not a descendant of the `velo_log` logger namespace, the plan's `velo_log`-scoped entry (`propagate: False`) does **not** cover it — only the root (`""`) logger reaches it, via propagation. This means the root-logger handler the plan treats as a minor design choice is actually load-bearing *today* for an existing, real call site — not just future-proofing for hypothetical app loggers.
- **Fix**: Correct the Current State Analysis to name both call sites (`velo_log/urls.py:33`, `gpx/views.py:18`). Add a manual verification step that exercises whatever `gpx/views.py` actually logs (check its call sites and levels) to confirm it surfaces correctly through the root handler with the same formatting guarantees as `velo_log.urls`, rather than assuming only `urls.py` needs checking.
- **Decision**: FIXED

### F3 — Root-handler attachment double-emits Django's own propagating loggers

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Phase 1 — Contract (root logger entry); Success Criteria (Manual Verification)
- **Detail**: Django's `"django"` logger does not set `propagate: False` (only `"django.server"` does) — per Django's own docs, "most loggers in Django propagate their messages to the root django logger." Once the plan's `LOGGING` dict attaches a handler to root, any `"django"`-logger record (already handled once by Django's own `console`/`mail_admins` handlers) will *also* reach the root handler and print a second time, in a different format. This is separate from F1's naming collision — it happens even after F1 is fixed. The plan's manual verification step only checks root-vs-`velo_log` duplication; it doesn't check django-vs-root duplication, so this would ship unnoticed.
- **Fix**: Add an explicit manual verification step that triggers an actual Django framework log (e.g. a 404 or a dev-server request log at `DEBUG=True`) and confirms whether it double-prints. Given this is a low-traffic personal project, double-printed framework lines during local dev may be an acceptable, explicitly-accepted tradeoff — but the plan must say so rather than silently claim "no duplicate lines" as a blanket guarantee.
- **Decision**: FIXED

### F4 — Custom `Filter` class location and dictConfig wiring unspecified

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Changes Required §1, Contract
- **Detail**: The plan says to use "a `logging.Filter` (not a bare format string)" to default a missing `media_root` field, but doesn't say where that class lives (inline in `settings.py`, or a new module) or its `dictConfig` wiring (the `"()"` callable-reference syntax `LOGGING["filters"]` needs). The Contract text also mixes `%(media_root)s` and `{media_root}` syntax in the same sentence, which is inconsistent with the `"style": "{"` decision already made earlier in the same section.
- **Fix**: Specify the filter class lives directly in `velo_log/settings.py` above the `LOGGING` dict, its exact `filter(self, record)` contract (`record.media_root = getattr(record, "media_root", "")`), and reference it via `"filters": {"media_root_default": {"()": "velo_log.settings.<ClassName>"}}`. Use `{media_root}` consistently (drop the `%(media_root)s` mention).
- **Decision**: FIXED

### F5 — Fixed `media_root=` suffix appears on every log line, including unrelated ones

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Lean Execution
- **Location**: Phase 1 — Contract, formatter `format` string
- **Detail**: The proposed format string (`"... {message} media_root={media_root}"`) appends `media_root=` to every record through this formatter, including `gpx/views.py`'s log calls (once F2 is addressed) and any future unrelated log call — most of the time rendering as a trailing `media_root=` with nothing after it.
- **Fix**: Low priority given the current 2-call-site scale; acceptable to ship as-is, but worth a one-line note in the plan acknowledging the tradeoff rather than leaving it implicit.
- **Decision**: FIXED
