"""Prove the suite actually bites — the automated form of `test-plan.md` §6.2's ritual.

`test-plan.md:166` ("Break the production line it guards, confirm the cell goes red for the
right reason, revert.") has a documented track record (`50b6abf`, `4e712b7`) but had never
been captured as anything that runs again on its own. This module is that capture: for each
shape in `tests/mutations.py`, spawn a real `pytest` subprocess with the mutation applied and
assert the named guard test goes red *for the named reason* — not merely "something failed".

Marked `bite_proof` and deselected by default (`pyproject.toml`'s `addopts`), because each
case pays a cold Django boot (~2-4 s); `uv run pytest -m bite_proof` is the CI step and the
local opt-in. The inventory assertion at the bottom is deliberately unmarked so it runs in
the default suite at effectively no cost — it never spawns a subprocess.
"""

import ast
import os
import re
import subprocess
import sys
from typing import NamedTuple

import pytest

from tests.mutations import MUTATION_SHAPES, MutationShape
from tests.test_assertion_strength import (
    REPO_ROOT,
    TEST_DIR,
    _class_test_methods,
    _module_test_functions,
)

# The `test-plan.md` §2 risk areas this phase claims to cover — named independently of
# `tests/mutations.py`'s registry so a shape silently dropped from the tuple (rather than
# deliberately un-covering a risk) is what turns this assertion red, not something it could
# pass by construction.
CLAIMED_RISK_AREAS = frozenset({"#1", "#2", "#3", "#5", "#7"})

FAILED_RE = re.compile(r"(\d+) failed")
ERROR_RE = re.compile(r"(\d+) error")
FAILURE_MARKED_LINE_RE = re.compile(r"^(?:>|E)\s")


def _failure_marked_lines(output: str) -> str:
    """The `> ` flow-marker line and `E ` explanation lines pytest prints for a failure.

    On failure, pytest also prints every source line of the guard function from its `def`
    down to the failing statement, as unmarked context — a fragment drawn from any assertion
    earlier than the one that actually tripped would appear there regardless of *why* the
    test failed. These two line kinds are the only ones that describe what actually happened,
    so matching a shape's fragment against just this text is what tells "this exact assertion
    failed" apart from "some other assertion failed and an earlier statement happens to share
    the fragment's text as source context".
    """
    return "\n".join(line for line in output.splitlines() if FAILURE_MARKED_LINE_RE.match(line))


GUARD_SUBPROCESS_TIMEOUT_SECONDS = 180

# pytest's own exit codes (https://docs.pytest.org/en/stable/reference/exit-codes.html) for
# every code a guard run might legitimately produce other than 1 ("tests failed", the only
# code a genuinely red guard exits with — see `test_the_mutation_shape_flips_its_guard_for_
# the_named_reason` below). Read explicitly rather than left to `failed_count >= 1` alone: a
# usage error or an uncollectable node id also leaves `failed_count == 0`, which without this
# would be misdiagnosed as "the guard was weakened" instead of "the harness itself is broken".
PYTEST_EXIT_CODE_MEANINGS: dict[int, str] = {
    0: "the guard node passed instead of failing — the mutation had no effect",
    2: "pytest was interrupted before it finished running the guard node",
    3: "pytest hit an internal error running the guard node",
    4: "pytest raised a usage error — the guard node id most likely does not resolve",
    5: "no tests were collected — the guard node id most likely does not resolve",
}


class _GuardRun(NamedTuple):
    returncode: int
    output: str


def _run_guard_under_mutation(shape: MutationShape) -> _GuardRun:
    """Run `shape`'s guard node in a subprocess with the mutation applied.

    `-o addopts=` neutralizes the default `-m "not bite_proof"` deselect (and anything else
    `addopts` grows later, such as `--cov`) so the child run is reproducible and does not
    write a competing coverage file. `-p no:cacheprovider` leaves nothing in
    `.pytest_cache`. Neither guard node is itself marked `bite_proof`, so the neutralization
    is defensive rather than presently load-bearing.

    `-o addopts=` only neutralizes the child's *own* `--cov`; pytest-cov's subprocess hook
    is driven by the `COV_CORE_*` environment variables, not `addopts`, so a parent run
    already under `--cov` (`pytest --cov -m bite_proof`, a plausible local invocation) would
    still instrument every child and drop `.coverage.*` files without this being stripped
    from the inherited environment.

    A mutation is deliberately broken production behavior — exactly the kind of change that
    can turn a short-circuit into a loop or a guard into a deadlock — so the child is bounded
    by `timeout=`. Without it, a hanging shape would block the parent (and, in CI, the
    runner's job) indefinitely with no diagnostic naming which shape hung.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("COV_CORE_")}
    env["VELOLOG_MUTATION"] = shape.name
    args = [
        sys.executable,
        "-m",
        "pytest",
        shape.guard_node_id,
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "--no-header",
        "-q",
    ]
    try:
        # S603: argv is entirely literal — this interpreter, "-m pytest", and shape's own
        # `guard_node_id`, which is a string constant declared in tests/mutations.py.
        result = subprocess.run(  # noqa: S603
            args,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=GUARD_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        # `text=True`/`encoding=` above guarantee `str`, not `bytes`, at runtime — the union
        # in `TimeoutExpired`'s stub is generic over both, unaware of those arguments.
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        pytest.fail(
            f"shape {shape.name!r}'s guard node {shape.guard_node_id} did not finish within "
            f"{GUARD_SUBPROCESS_TIMEOUT_SECONDS}s — the mutation likely turned a "
            f"short-circuit into a loop or a guard into a deadlock rather than a clean "
            f"failure:\n{stdout}{stderr}"
        )
    return _GuardRun(result.returncode, result.stdout + result.stderr)


@pytest.mark.bite_proof
@pytest.mark.parametrize("shape", MUTATION_SHAPES, ids=lambda s: s.name)
def test_the_mutation_shape_flips_its_guard_for_the_named_reason(shape: MutationShape) -> None:
    run = _run_guard_under_mutation(shape)
    output = run.output

    if run.returncode != 1:
        reason = PYTEST_EXIT_CODE_MEANINGS.get(
            run.returncode, f"pytest exited {run.returncode}, an unrecognized code"
        )
        pytest.fail(
            f"shape {shape.name!r}'s guard node {shape.guard_node_id} exited "
            f"{run.returncode} instead of 1 (tests failed) — {reason}:\n{output}"
        )

    error_match = ERROR_RE.search(output)
    error_count = int(error_match.group(1)) if error_match else 0
    assert error_count == 0, (
        f"shape {shape.name!r} produced {error_count} pytest error(s) instead of a clean "
        f"failure — the mutation likely broke collection or import rather than the guard "
        f"test's own assertion, which proves nothing about the guard:\n{output}"
    )

    failed_match = FAILED_RE.search(output)
    failed_count = int(failed_match.group(1)) if failed_match else 0
    assert failed_count >= 1, (
        f"shape {shape.name!r} produced no failures with {shape.attribute} in "
        f"{shape.module_path} mutated — either {shape.guard_node_id} was weakened (it no "
        f"longer asserts the behavior this mutation breaks), or the patch target has moved "
        f"(the view/receiver no longer reads {shape.module_path}.{shape.attribute}):\n{output}"
    )

    guard_test_name = shape.guard_node_id.split("::", 1)[1]
    assert guard_test_name in output, (
        f"shape {shape.name!r} failed, but not by way of {shape.guard_node_id} — the "
        f"failure output never names the guard test:\n{output}"
    )

    failure_lines = _failure_marked_lines(output)
    assert shape.fragment in failure_lines, (
        f"shape {shape.name!r}'s guard failed, but not for the named reason — the expected "
        f"fragment {shape.fragment!r} is absent from the failure-marked lines, which means "
        f"either the guard was weakened (a different assertion in it failed first) or the "
        f"patch target moved:\n{output}"
    )


def _guard_node_function(guard_node_id: str) -> tuple[str, str]:
    """(relative path, function name) a guard node id resolves to, its `[...]` id stripped.

    A shape may pin a specific parametrization (e.g. `test_foo[trips:detail-get]`) to
    narrow which cell of a parametrized test must go red; the AST inventory below only
    knows about the underlying function definition, so the parametrize suffix is stripped
    before checking that the node id resolves to a real test.
    """
    path, function_id = guard_node_id.split("::", 1)
    function_name = function_id.split("[", 1)[0]
    return path, function_name


def _all_test_function_names() -> set[tuple[str, str]]:
    """(relative path, test name) for every `test_*` function or method under `tests/`.

    Reuses Phase 2's AST parse — `_module_test_functions` and `_class_test_methods` are the
    same functions `tests/test_assertion_strength.py::_collect_analysis` uses to enumerate a
    module's tests, top-level and class-based — rather than `pytest --collect-only`, which
    would run a whole-suite collection pass inside the default suite: exactly the cost the
    `bite_proof` marker and `addopts` exist to keep out of the local edit loop.
    """
    names: set[tuple[str, str]] = set()
    for path in sorted(TEST_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(REPO_ROOT).as_posix()
        test_fns, _helper_fns = _module_test_functions(tree)
        names.update((relative, fn.name) for fn in test_fns)
        names.update((relative, name) for name, _fn in _class_test_methods(tree))
    return names


def test_every_risk_area_has_a_shape_and_every_guard_node_resolves() -> None:
    covered_risks = {shape.risk for shape in MUTATION_SHAPES}
    missing_risks = CLAIMED_RISK_AREAS - covered_risks
    assert not missing_risks, (
        "tests/mutations.py's MUTATION_SHAPES no longer covers every risk area this phase "
        f"claims: missing {sorted(missing_risks)}"
    )

    all_test_functions = _all_test_function_names()
    unresolved = [
        shape.guard_node_id
        for shape in MUTATION_SHAPES
        if _guard_node_function(shape.guard_node_id) not in all_test_functions
    ]
    assert not unresolved, (
        "the following guard node ids in tests/mutations.py's MUTATION_SHAPES do not "
        "resolve to a test function that exists under tests/:\n"
        + "\n".join(f"  {node_id}" for node_id in unresolved)
    )
