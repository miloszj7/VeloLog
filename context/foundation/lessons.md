# Lessons

Recurring rules and pitfalls accumulated across changes. Read this file at the start of
every `/10x-implement` run and let it shape implementation choices. Add to it via
`/10x-lesson` when a new class of bug or design pitfall surfaces.

1. **A test whose name claims an assertion must actually make it.**
   Source: `impl-review.md` F2 (`context/archive/2026-08-22-user-registration-login/`).
   Why: `test_login_with_invalid_credentials_shows_error` asserted only a re-rendered
   200, never the error itself — a gap that let a genuine bug (F1, below) reach
   `master` with every gate green.

2. **Render `{{ form.non_field_errors }}` in every form template.**
   Source: `impl-review.md` F1.
   Why: omitting it renders a blank form on invalid submission with no feedback to the
   user — a critical UX defect that automated checks (which only assert status codes)
   do not catch on their own.

3. **A high coverage percentage can conceal the one uncovered line that matters.**
   Source: `impl-review.md` F4, F10.
   Why: a page that is never rendered under test (e.g. the authenticated-chrome branch
   of a template) can sit inside an app already at or above the coverage target,
   because coverage measures lines executed, not scenarios proven.

4. **Widen `[tool.coverage.run] source` whenever a new package ships.**
   Source: `impl-review.md` F10.
   Why: `fail_under` passes regardless of how untested an unmeasured package is —
   the gate is silently defeated the moment a new app's code isn't in `source`.

5. **Update `AGENTS.md` and roadmap status in the same slice that invalidates them.**
   Source: `impl-review.md` F7.
   Why: `AGENTS.md` loads every session — a stale claim (e.g. a wrong coverage scope)
   actively misdirects the next agent rather than merely being out of date.

6. **Normalize on write and compare case-insensitively for user-supplied identifiers.**
   Source: `impl-review.md` F3.
   Why: a case-sensitive uniqueness check (e.g. on email) is trivially bypassable by
   varying case, defeating the uniqueness guarantee it exists to enforce.

7. **Never write to `context/archive/`.**
   Source: `CLAUDE.md`, `AGENTS.md` Hard Rules.
   Why: archived changes are immutable records of what shipped; open a new change with
   `/10x-new` instead of editing history.

8. **Fix commits precede the commit recording the decisions describing them.**
   Source: `~/.claude/rules/git-workflow.md` (Committing triage/review fixes
   one-finding-one-commit).
   Why: a decision commit ("finding N: FIXED") sitting before its own fix reads as a
   lie when a reviewer walks the log in order.

9. **A migration's absence cannot be caught by CI — generate and commit it by hand,
   and verify with `makemigrations --check --dry-run`.**
   Source: `context/changes/create-and-list-trips/plan.md` (Phase 1, Critical
   Implementation Details).
   Why: `manage.py check` passes with a model/schema mismatch, and the deploy
   pipeline runs `migrate` unattended before starting the app server — a forgotten
   migration file ships green through every automated gate and only surfaces as a
   production outage (`no such column`) after deploy.

10. **A `post_delete` receiver is what makes a cascade's rows exist at all — file cleanup
    on cascade is impossible without one.**
    Source: `context/changes/edit-and-delete-trip/plan.md` (Key Discoveries, Phase 2),
    verified against `django/db/models/deletion.py` in the installed source.
    Why: `Collector.can_fast_delete()` returns `False` only when a model has
    `pre_delete`/`post_delete` listeners. With no receiver, a parent's cascade
    fast-deletes the child rows in one SQL statement and **never materializes them**, so
    there is no instance to read a file path or any other external key from. Registering
    the receiver is the mechanism, not merely the hook — and it must schedule its storage
    work with `transaction.on_commit`, because `post_delete` fires inside the collector's
    transaction and a delete performed there is already gone if the block later raises.

11. **A docstring that describes an assertion is a claim the body must fully honour, not
    partially.**
    Source: `context/changes/testing-gate-credibility/plan.md` (Phase 1, finding on
    `test_put_is_rejected_as_a_disallowed_method`); see also `tests/test_assertion_strength.py`
    and lesson #1.
    Why: the test's docstring claimed the assertion "pins the pair of verbs that stay open" —
    a positive `Allow` pin — while the body only asserted `"PUT" not in ...headers["Allow"]`,
    a negative-only check that doesn't deliver that claim. The docstring is what the next
    reader trusts instead of re-deriving the assertions from the body, so an overclaiming
    docstring is worse than an absent one: lesson #1 is a test whose *name* claims an
    assertion it doesn't make; this is the same shape one level deeper, in the docstring,
    on a test whose name was accurate throughout.
