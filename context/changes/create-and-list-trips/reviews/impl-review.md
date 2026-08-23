<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Create and List Trips (S-02)

- **Plan**: `context/changes/create-and-list-trips/plan.md`
- **Scope**: Phases 1–5 of 5 (full plan; Phase 5 manual production-verification items 5.7–5.13 legitimately pending)
- **Date**: 2026-08-23
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 5 observations
- **Commits reviewed**: `84256db` … `7ae2441` (working tree clean)

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

### Automated success criteria — all re-run for this review

| Check | Result |
|---|---|
| `makemigrations --check --dry-run` | ✅ exit 0, "No changes detected" |
| `manage.py check` | ✅ 0 issues; no `models.W042` |
| `pytest --cov` | ✅ 26 passed, 93.33% coverage, `fail_under = 80` met with `trips` in scope |
| `ruff check .` | ✅ clean (with the `S608` ignore removed and `main.py` deleted) |
| `black --check` / `isort --check-only` | ✅ clean |
| `mypy .` (strict + django-stubs) | ✅ 0 issues, 30 files |
| `manage.py check --deploy` (DEBUG=False) | ✅ exit 0 — 2 pre-existing HSTS warnings, untouched by this slice |
| No dangling `accounts:landing` / `landing.html` | ✅ none outside historical `context/` docs |
| Zero `# type: ignore` / `# noqa` / `class=` | ✅ invariants hold |

No rubber-stamped manual items detected: every `[x]` manual criterion has corroborating evidence in the
diff, and the Engineering Backlog row attributed to "found during Phase 3 manual verification"
(`roadmap.md`, future-dated `TripForm`) is direct evidence that manual testing genuinely ran.

### Scope Discipline — all 12 boundaries verified clean

No edit/delete views · no GPX/file storage/`MEDIA_ROOT` · no detail view · no filtering, sorting, search,
or pagination · no visibility toggle · **zero CSS and zero `class=` attributes across five new templates** ·
no custom `AUTH_USER_MODEL` · no `services.py`/repository layer · no `LOGGING` config · no new CI job
(one line appended to the pre-existing gate step, exactly as the plan's stated exception permits) ·
no new dependencies (`uv.lock` absent from the branch diffstat).

### Security posture

No CRITICAL findings. Ownership is enforced server-side at both boundaries: `owner` is excluded from
`TripForm.Meta.fields` (`trips/forms.py:18`) and assigned from `request.user` (`trips/views.py:40`),
while reads are scoped by `get_queryset()` (`trips/views.py:28`). `LoginRequiredMixin` is first in the
base list on both views, so its `dispatch()` genuinely takes effect. CSRF tokens present on all four POST
forms. Zero `|safe` / `mark_safe` / `autoescape off` / `.raw()` / `.extra()` / `cursor()` anywhere.
The migration is a single purely-additive `CreateModel` matching the model field for field.

## Findings

### F1 — Cross-user isolation test's body assertion can never fail

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `tests/trips/test_trip_list.py:30`
- **Detail**: The plan's Phase 3 #6 contract requires the isolation test to assert "against
  `response.context["object_list"]` **as well as** the decoded body, so a template-only pass cannot fake
  it", and its Caution cites lesson #1 (a test whose name claims an assertion must make it). The
  `object_list` half (line 29) is sound. The body half is vacuous: the fixture trip is named
  `"Other's Trip"`, and Django autoescapes the apostrophe — verified against this repo's Django,
  `escape("Other's Trip")` → `'Other&#x27;s Trip'`. The raw needle is therefore absent from the rendered
  body whether the trip leaks or not. **Empirically confirmed**: a throwaway test that gives the trip to
  the *requesting* user (so it definitively renders — `Other&#x27;s Trip` is present in the body) still
  passes `assert "Other's Trip" not in response.content.decode()`. The escaping asymmetry is easy to miss
  because the sibling assertion at line 17 uses `"Alps Loop"`, where `escape()` is a no-op and the body
  assertion is genuinely real. Isolation itself *is* still proven by line 29 — this is a test-integrity
  defect, not a security hole.
- **Fix**: Rename the other user's trip to a needle with no escapable characters (e.g.
  `"Other Rider Trip"`) so the body assertion becomes load-bearing.
  - Strength: Restores the exact protection the plan's Caution asked for, and matches how line 17 already
    works; one-word change, no new test.
  - Tradeoff: None — the escaped-form alternative (`Other&#x27;s Trip`) would work too but couples the
    test to Django's escaping implementation.
  - Confidence: HIGH — the vacuity is empirically demonstrated, not inferred.
  - Blind spot: None significant.
- **Decision**: PENDING

### F2 — The plan's own prose about `ModelForm`/`ModelAdmin` subscriptability is factually wrong

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `context/changes/create-and-list-trips/plan.md:149`, `:261`
- **Detail**: The plan asserts `ModelAdmin` "subscripts directly under django-stubs, like `ModelForm`"
  (`:149`) and `TripForm(forms.ModelForm[Trip])` — "`ModelForm` subscripts directly, unlike the generic
  views (`accounts/forms.py:7` shows the pattern)" (`:261`). Both claims are false. Verified at runtime
  against this repo's Django 6.0.5: `forms.ModelForm[...]` → `TypeError: type 'ModelForm' is not
  subscriptable`; `admin.ModelAdmin[...]` → the same. Only `UserCreationForm` is subscriptable, because it
  alone carries `__class_getitem__` — which is why the cited `accounts/forms.py:7` works and does not
  generalize. Coding the plan literally would have raised at import time. The implementation correctly
  used a `TYPE_CHECKING` shim in `trips/forms.py:7-10` and `trips/admin.py:7-10` instead. **The code is
  right and the plan is wrong** — but the plan explicitly intends this pattern to propagate to S-03 and
  S-04, so the false claim is a live trap for the next slice.
- **Fix**: Correct both plan lines to state that `ModelForm` and `ModelAdmin` require the same
  `TYPE_CHECKING` shim as the generic CBVs, and that only `UserCreationForm` subscripts directly.
  - Strength: The plan is the archived record S-03/S-04 will read; fixing it removes an import-time
    `TypeError` waiting to happen. The shipped shim is already the correct pattern to point at.
  - Tradeoff: Editing a plan post-implementation, though this is a factual correction, not a scope change.
  - Confidence: HIGH — subscriptability verified empirically for all three classes.
  - Blind spot: None significant. (Worth also considering as a durable lesson, since `lessons.md` is what
    `/10x-implement` re-reads — the triage "Record as lesson" path covers that.)
- **Decision**: PENDING

### F3 — Missing method/class docstrings, regressing an S-01 review fix

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `trips/views.py:27`, `trips/views.py:39`, `trips/admin.py:14`
- **Detail**: The `accounts/` baseline carries a one-line Google-style docstring on **every** public
  callable — `SignUpView.form_valid` (`accounts/views.py:26`), `SignUpForm.clean_email`
  (`accounts/forms.py:17`), `healthz` (`velo_log/urls.py:27`) — and `research.md:82` records that this was
  retro-fixed as S-01 review finding F8. In `trips/`, the classes are documented but
  `TripListView.get_queryset`, `TripCreateView.form_valid`, and the `TripAdmin` class are not. Ruff does
  not enforce this (`select` omits `D`), so no gate catches the regression.
- **Fix**: Add a one-line docstring to `TripListView.get_queryset`, `TripCreateView.form_valid`, and
  `TripAdmin`, matching the `accounts/` wording style.
- **Decision**: PENDING

### F4 — `change.md` status never advanced past `implementing`

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: `context/changes/create-and-list-trips/change.md:4`
- **Detail**: Phase 5 #5 planned "`status` advances and `updated` is stamped to the completion date". The
  Phase 5 commit `9a5070b` never touched `change.md`; `status: implementing` and `updated: 2026-08-23` are
  both leftovers from the Phase 1 commit `84256db`. `updated` happens to be correct only because the whole
  slice landed in a single day. This is the one planned edit that never landed — of roughly fifty. It is
  the reason Plan Adherence is WARNING rather than PASS, and the reason it is not FAIL is that a one-field
  doc stamp is not "major drift".
- **Fix**: Already resolved — this review stamps `status: impl_reviewed` and refreshes `updated`, which
  supersedes the planned advance. No further action needed.
- **Decision**: PENDING

### F5 — Admin changelist N+1 on the `owner` FK

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: `trips/admin.py:15`
- **Detail**: `list_display = ("name", "date", "owner")` puts a FK in the changelist without
  `list_select_related`, producing one extra `User` query per row. Blast radius is small — superuser-only,
  and no production superuser exists yet (Phase 5 #6 adds creating one) — but it is a real N+1 on the one
  page the plan justified `admin.py` for as a production repair path.
  Note: the list *view* is clean — `trip_list.html:9-13` touches only `name`, `date`, and `description`,
  never `trip.owner`, so `select_related` is genuinely unnecessary there.
- **Fix**: Add `list_select_related = ("owner",)` to `TripAdmin`.
- **Decision**: PENDING

### F6 — Test hygiene: unused fixtures, discarded login result, one untested path

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: `tests/trips/test_trip_model.py:9,17,25,36`; `tests/conftest.py:20`
- **Detail**: Three small items, all in the same area:
  1. `test_trip_model.py` inlines `User.objects.create_user(username="rider", ...)` four times instead of
     taking the `rider` fixture this same branch added at `tests/conftest.py:8-10`. Chronologically
     explicable — Phase 1 wrote these tests before Phase 3 created the fixtures — but it leaves the only
     trips test file that ignores `conftest.py`.
  2. `tests/conftest.py:20` discards `client.login(...)`'s return value. If the fixture credentials ever
     drift, every trips test fails with a confusing 302-to-login rather than at the fixture.
     (Positive: the branch correctly uses `client.login()`, not `force_login`, per house convention.)
  3. An unauthenticated **GET** of `trips:create` is untested — only the POST path
     (`test_trip_creation.py:68`) is. `trips/views.py` reports 100% line coverage, so this is exactly the
     scenario-vs-line gap lesson #3 warns about.
- **Fix**: Take `rider: User` as a parameter in the four model tests, `assert client.login(...)` in the
  fixture, and add one test for an unauthenticated GET of `trips:create`.
- **Decision**: PENDING

### F7 — The `?next=` chain works only by accident of an actionless form

- **Severity**: 📝 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `accounts/templates/accounts/login.html:7`
- **Detail**: The login form is `<form method="post">` with no `action`, so it re-posts to the current URL
  *including* `?next=/trips/`, which `LoginView.get_redirect_url()` then reads from `request.GET`. There is
  no `<input type="hidden" name="next" value="{{ next }}">` — which Django's own default login template
  carries — and no test follows the chain end to end: `test_trip_list.py:42` and
  `test_login_logout.py:52` both assert the redirect *Location* only, never that logging in from it lands
  on `/trips/`. Adding an explicit `action="{% url 'login' %}"` later would silently break the redirect
  with every gate green. The behavior is pre-existing from S-01, but Phase 2 retrofitted this file and
  Phase 4 made `?next=` the load-bearing path from the newly-routed site root.
- **Fix A ⭐ Recommended**: Add the hidden `next` field to `login.html` and one end-to-end test that GETs
  `/trips/`, follows to login, POSTs credentials, and asserts it lands on `/trips/`.
  - Strength: Removes the implicit dependency on form-action behavior and covers the chain that Phase 4's
    root redirect now depends on; matches Django's own login template.
  - Tradeoff: Touches an `accounts/` template this slice was otherwise done with, and adds a test to a
    suite that already passes.
  - Confidence: HIGH — the mechanism is well-understood and the missing coverage is verifiable.
  - Blind spot: Haven't confirmed whether `{{ next }}` is populated in this project's login context
    (it should be, via `LoginView`'s `redirect_field_name`) — worth checking when applying.
- **Fix B**: Add only the end-to-end test, leaving the template as-is.
  - Strength: Zero behavior change; the test alone would catch the breakage if anyone adds an `action`.
  - Tradeoff: Leaves the fragility in place rather than removing it.
  - Confidence: MEDIUM — a test guards the regression but does not eliminate the implicit coupling.
  - Blind spot: None significant.
- **Decision**: PENDING

### F8 — CI still deploys to production without running the test suite

- **Severity**: 📝 OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: `.github/workflows/deploy.yml:20-25`
- **Detail**: The merge gate runs `manage.py check` plus the new `makemigrations --check --dry-run`, then
  proceeds to `railway up`. `pytest` never runs in CI, so a red suite pushes straight to production, and
  the coverage gate this slice correctly widened to include `trips` (`pyproject.toml:61`, lesson #4) is
  never read by any automation. **This is not drift** — the plan deliberately excluded new CI jobs
  ("landing it on the same deploy as the first production migration stacks two risky firsts") and filed it
  on the Engineering Backlog with the trigger "Before S-03". It is recorded here because it is the widest
  blast radius on the branch by a distance, and because that trigger is now the *next* slice.
- **Fix A ⭐ Recommended**: Honor the plan's deferral — leave CI as-is for this deploy, and treat the
  backlog row as due before S-03 starts.
  - Strength: Respects a documented, reasoned decision with a trigger that has not yet fired; keeps the
    first production-migration deploy to one risky first instead of two.
  - Tradeoff: This deploy ships with tests unverified by automation (mitigated: all gates were re-run
    locally and green for this review).
  - Confidence: HIGH — the deferral is explicit in the plan's "What We're NOT Doing" and filed with a
    trigger, so nothing is being forgotten.
  - Blind spot: Relies on the S-03 planning step actually reading the Engineering Backlog.
- **Fix B**: Add `uv run pytest --cov` to the existing gate job now, before the Railway steps.
  - Strength: Closes the gap immediately; the plan already accepted one edit to this same step, so the
    marginal risk is a job that takes longer, not a new failure mode.
  - Tradeoff: Overrides a deliberate plan decision, and the workflow triggers on push to `master` only —
    so it would still catch mistakes post-merge, not pre-merge, which is the half the backlog row is
    really about.
  - Confidence: MEDIUM — cheap and safe, but only delivers part of what the backlog row scopes.
  - Blind spot: Haven't verified CI runtime headroom or whether the runner has everything `pytest` needs
    beyond `SECRET_KEY`.
- **Decision**: PENDING

## Notable positives

- The `TYPE_CHECKING` shim caught three genuine generics (`ListView`, `CreateView`,
  `SuccessMessageMixin`) and correctly left `LoginRequiredMixin` un-shimmed. The unplanned
  `cast(User, self.request.user)` (`trips/views.py:28,40`) is necessary under `mypy --strict` and is not a
  suppression, so the repo's zero-`type: ignore` invariant survives its first real pressure test.
- `template_name` is set explicitly on `TripCreateView` — the asymmetric failure the plan's Caution
  singled out (a valid POST redirects without rendering, so the happy path would have passed green while
  `GET /trips/new/` 500'd) was avoided.
- Lesson #2 is fully honored: `{{ form.non_field_errors }}` present in all three form templates
  (`trip_form.html:9`, `login.html:9`, `signup.html:9`).
- The owner-override test genuinely proves what it claims — it POSTs `other_rider.pk` with two users in
  play and asserts `trip.owner == rider`.
- The same-date ordering test asserts the exact `[second, first]` list, proving the `-id` tiebreak rather
  than merely "no crash".
- The migration is verbatim `makemigrations` output (the black-style wrapping is Django's own
  `run_formatters()`), purely additive, and matches the model field for field.
