"""Fail the suite when a request-cycle test asserts nothing beyond a status code.

A bare `assert response.status_code == 404` passes against a view that read, wrote or
deleted the object it was refusing and only refused *afterwards* — the exact shape
`lessons.md` #1 records and this project's own history caught by hand more than once
(`tests/test_ownership_matrix.py`'s module docstring). Nothing before this test stopped a
third status-only test from creeping back in once a reviewer stopped looking for the
pattern by eye.

The population is scoped to **request-cycle tests** — tests that issue a call through the
Django test client — on purpose. `tests/gpx/test_gpx_parsing.py` has a dozen tests with no
`assert` statement at all, because `pytest.raises` *is* the assertion; a rule demanding a
non-status assert of them would be wrong about what those tests are. Settings tests, model
tests and signal-receiver tests that call the receiver directly are equally out of scope —
none of them describe a request/response cycle, so "beyond the status code" has no meaning
for them.

Two refinements keep the population precise rather than merely broad:

- **Positional.** An assertion *before* the last request the test issues is a setup guard
  (e.g. `assert track.file.name is not None` ahead of the request in
  `test_gpx_download.py`), not a behavior probe, and is not counted. The rule only looks at
  or after the act.
- **Delegation-aware.** A probe can be handed off — `route.probe(target, response)` in
  `tests/test_ownership_matrix.py` is a probe even though the probing logic lives in a
  function the test never names — so a call at or after the act that is handed the response
  object counts, and so does a call to a module-local helper whose own body contains a
  non-status assertion.

The waiver inventory below is the escape hatch for the one real exception: a test whose
entire subject *is* a sequence of status codes (a cache short-circuiting a slow path). Both
directions are asserted — a real finding not in the inventory, and an inventory entry that
no longer earns its keep — so the inventory itself cannot rot silently, the same guarantee
`tests/test_coverage_scope.py` and `tests/test_ownership_matrix.py::
test_every_object_scoped_route_is_classified` already give their own declarations.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = REPO_ROOT / "tests"

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef

# The Django test client methods that issue a request. `generic` and `trace` are included
# even though nothing in this suite calls them today, so a future test using either is
# still recognised as request-cycle.
CLIENT_VERB_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace", "generic"}
)

# (relative path, test name, reason). Checked both ways: a finding not listed here fails
# the suite, and a listed entry whose test no longer exists or no longer trips the rule
# fails it too — see `test_the_waiver_inventory_matches_reality` below.
WAIVER_INVENTORY: tuple[tuple[str, str, str], ...] = (
    (
        "tests/test_media_storage.py",
        "test_healthz_serves_a_cached_verdict_instead_of_reprobing",
        "the behavior under test genuinely is a status sequence — 200, then 200 with the "
        "storage backend broken, then 500 after a cache clear — and the middle 200 is the "
        "whole proof that the cache short-circuited the probe; any added probe would be "
        "contrived",
    ),
)


def _walk_body(node: ast.AST) -> Iterator[ast.AST]:
    """Depth-first walk of `node`'s subtree that does not descend into nested defs.

    Behaves like `ast.walk`, except a nested `FunctionDef`/`AsyncFunctionDef`/`ClassDef`/
    `Lambda` is yielded (as a child of whatever contains it) but never descended into —
    the population and the rule both operate one function at a time, so a helper's own
    body must be inspected only by a deliberate, separate call, never accidentally pulled
    in as if it were part of the caller.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if isinstance(child, FuncDef | ast.ClassDef | ast.Lambda):
                continue
            stack.append(child)


def _mentions_client(node: ast.expr) -> bool:
    return any(isinstance(n, ast.Name) and "client" in n.id.lower() for n in ast.walk(node))


def _is_direct_act_call(call: ast.Call) -> bool:
    """`<something containing "client">.<verb>(...)` — the literal request-issuing shape."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr in CLIENT_VERB_METHODS):
        return False
    return _mentions_client(func.value)


def _is_delegate_act_call(call: ast.Call, act_helper_names: frozenset[str]) -> bool:
    func = call.func
    return isinstance(func, ast.Name) and func.id in act_helper_names


def _is_act_call(call: ast.Call, act_helper_names: frozenset[str]) -> bool:
    return _is_direct_act_call(call) or _is_delegate_act_call(call, act_helper_names)


def _client_param_names(fn: FuncDef) -> frozenset[str]:
    args = fn.args
    all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg is not None:
        all_args.append(args.vararg)
    if args.kwarg is not None:
        all_args.append(args.kwarg)
    return frozenset(a.arg for a in all_args if "client" in a.arg.lower())


def _is_act_helper(fn: FuncDef) -> bool:
    """True when calling `fn` with a client-ish argument issues a request.

    Resolved one level: only `fn`'s own body is inspected, never a helper `fn` itself
    delegates to. `tests/test_ownership_matrix.py::_issue` is the case this exists for — it
    dispatches by `getattr(client, verb)` rather than a literal `.get`/`.post` call, so the
    getattr shape is recognised explicitly rather than missed by the direct-call check.
    """
    client_params = _client_param_names(fn)
    if not client_params:
        return False
    for node in _walk_body(fn):
        if not isinstance(node, ast.Call):
            continue
        if _is_direct_act_call(node):
            return True
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in client_params
        ):
            return True
    return False


def _has_nonstatus_assert(fn: FuncDef) -> bool:
    return any(
        isinstance(node, ast.Assert) and not _is_status_only_assert(node.test)
        for node in _walk_body(fn)
    )


def _is_status_only_assert(test: ast.expr) -> bool:
    """True for a comparison that carries no information beyond `status_code`.

    Covers `<chain>.status_code <op> <int/bool literal>`, `<chain>.status_code in/not in
    <tuple/list of int constants>`, and — fail closed rather than fail open — a comparison
    whose only non-`status_code` side is a bare name or dotted attribute (`expected_status`,
    `HTTPStatus.OK`). The AST cannot tell what a name or attribute resolves to, so it cannot
    be *proven* to add information the way a header, a body, or a DB query would; treating
    it as a probe by default let both idioms slip past the rule unclassified, passing "by
    construction" the same way a genuine probe does, which they are not. Anything else (a
    header, a body, a DB query, a second attribute compared against something other than
    `status_code`, a string literal) is a probe by construction.
    """
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    op, left, right = test.ops[0], test.left, test.comparators[0]

    def is_status_chain(node: ast.expr) -> bool:
        return isinstance(node, ast.Attribute) and node.attr == "status_code"

    def is_int_literal(node: ast.expr) -> bool:
        return isinstance(node, ast.Constant) and isinstance(node.value, (int, bool))

    def is_unclassifiable(node: ast.expr) -> bool:
        return isinstance(node, (ast.Name, ast.Attribute))

    def is_int_constant_collection(node: ast.expr) -> bool:
        return bool(
            isinstance(node, (ast.Tuple, ast.List))
            and node.elts
            and all(is_int_literal(elt) for elt in node.elts)
        )

    def is_status_only_value(node: ast.expr) -> bool:
        return is_int_literal(node) or is_unclassifiable(node)

    if isinstance(op, (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)):
        return (is_status_chain(left) and is_status_only_value(right)) or (
            is_status_chain(right) and is_status_only_value(left)
        )
    if isinstance(op, (ast.In, ast.NotIn)) and is_status_chain(left):
        return is_int_constant_collection(right) or is_unclassifiable(right)
    return False


def _dotted_call_name(node: ast.expr) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _is_probe_with(node: ast.With) -> bool:
    """`pytest.raises(...)` or `django_assert_num_queries(...)` — a probe, not a status check.

    Either is a claim about behavior a status code cannot express (an exception was raised,
    the query count was exactly N), so a `with` block built from either counts on sight.
    """
    for item in node.items:
        expr = item.context_expr
        if not isinstance(expr, ast.Call):
            continue
        name = _dotted_call_name(expr.func)
        if name.endswith("raises") or "assert_num_queries" in name:
            return True
    return False


def _call_references_any(call: ast.Call, names: frozenset[str]) -> bool:
    if not names:
        return False
    arguments = [*call.args, *(kw.value for kw in call.keywords)]
    return any(
        isinstance(n, ast.Name) and n.id in names for arg in arguments for n in ast.walk(arg)
    )


def _response_variable_names(fn: FuncDef, act_helper_names: frozenset[str]) -> frozenset[str]:
    """Names the act's result is assigned to — what a delegated probe is handed.

    Only simple `name = <act call>` assignments are tracked; the suite's own idiom never
    destructures a response, so a tuple or attribute target would signal something this
    audit does not understand rather than something to chase further.
    """
    names: set[str] = set()
    for node in _walk_body(fn):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if any(
            isinstance(n, ast.Call) and _is_act_call(n, act_helper_names)
            for n in ast.walk(node.value)
        ):
            names.add(target.id)
    return frozenset(names)


def _last_act_lineno(fn: FuncDef, act_helper_names: frozenset[str]) -> int | None:
    linenos = [
        node.lineno
        for node in _walk_body(fn)
        if isinstance(node, ast.Call) and _is_act_call(node, act_helper_names)
    ]
    return max(linenos) if linenos else None


def _has_behavior_probe(
    fn: FuncDef,
    last_act_lineno: int,
    response_names: frozenset[str],
    delegating_helper_names: frozenset[str],
) -> bool:
    for node in _walk_body(fn):
        lineno = getattr(node, "lineno", None)
        if lineno is None or lineno < last_act_lineno:
            continue
        if isinstance(node, ast.Assert):
            if not _is_status_only_assert(node.test):
                return True
        elif isinstance(node, ast.With):
            if _is_probe_with(node):
                return True
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if _call_references_any(call, response_names):
                return True
            if isinstance(call.func, ast.Name) and call.func.id in delegating_helper_names:
                return True
    return False


def _module_test_functions(tree: ast.Module) -> tuple[list[FuncDef], list[FuncDef]]:
    """Split a module's top-level defs into (`test_*` functions, everything else)."""
    tests: list[FuncDef] = []
    helpers: list[FuncDef] = []
    for node in tree.body:
        if not isinstance(node, FuncDef):
            continue
        (tests if node.name.startswith("test_") else helpers).append(node)
    return tests, helpers


def _collect_analysis() -> dict[tuple[str, str], bool | None]:
    """Map (relative path, test name) -> probe_found, or `None` if out of population."""
    results: dict[tuple[str, str], bool | None] = {}
    for path in sorted(TEST_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(REPO_ROOT).as_posix()
        test_fns, helper_fns = _module_test_functions(tree)
        act_helper_names = frozenset(f.name for f in helper_fns if _is_act_helper(f))
        delegating_helper_names = frozenset(f.name for f in helper_fns if _has_nonstatus_assert(f))

        for fn in test_fns:
            last_act = _last_act_lineno(fn, act_helper_names)
            if last_act is None:
                continue  # not a request-cycle test — out of population, unexamined
            response_names = _response_variable_names(fn, act_helper_names)
            probe_found = _has_behavior_probe(fn, last_act, response_names, delegating_helper_names)
            results[(relative, fn.name)] = probe_found
    return results


def test_the_population_is_non_empty() -> None:
    """Guard the guard: a heuristic that silently matched nothing would pass for free."""
    analysis = _collect_analysis()
    population = {key: found for key, found in analysis.items() if found is not None}
    assert population, (
        "the request-cycle population is empty — the client-call detection in "
        "test_assertion_strength.py no longer matches anything under tests/, which means "
        "this audit is not examining any test at all"
    )


def test_every_request_cycle_test_asserts_more_than_a_status_code() -> None:
    analysis = _collect_analysis()
    waived = {(path, name) for path, name, _reason in WAIVER_INVENTORY}

    findings = sorted(
        key for key, probe_found in analysis.items() if probe_found is False and key not in waived
    )
    assert not findings, (
        "the following request-cycle tests assert only a status code, which passes against "
        "a view that did the work and refused afterwards — add a status-plus-state/content "
        "probe at or after the request (test-plan.md §6.2), or add a justified waiver to "
        "WAIVER_INVENTORY in tests/test_assertion_strength.py:\n"
        + "\n".join(f"  {path}::{name}" for path, name in findings)
    )


def test_the_waiver_inventory_matches_reality() -> None:
    analysis = _collect_analysis()

    stale: list[str] = []
    for path, name, _reason in WAIVER_INVENTORY:
        probe_found = analysis.get((path, name))
        if probe_found is None:
            stale.append(f"{path}::{name} — no longer exists as a request-cycle test")
        elif probe_found is True:
            stale.append(f"{path}::{name} — now asserts more than a status code; drop the waiver")

    assert not stale, (
        "WAIVER_INVENTORY in tests/test_assertion_strength.py carries entries that no "
        "longer earn their keep:\n" + "\n".join(f"  {line}" for line in stale)
    )
