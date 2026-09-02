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

import pytest

from tests.mutations import MUTATION_SHAPES, MutationShape
from tests.test_assertion_strength import REPO_ROOT, TEST_DIR, _module_test_functions

# The `test-plan.md` §2 risk areas this phase claims to cover — named independently of
# `tests/mutations.py`'s registry so a shape silently dropped from the tuple (rather than
# deliberately un-covering a risk) is what turns this assertion red, not something it could
# pass by construction.
CLAIMED_RISK_AREAS = frozenset({"#1", "#2", "#3", "#5", "#7"})

FAILED_RE = re.compile(r"(\d+) failed")
ERROR_RE = re.compile(r"(\d+) error")


def _run_guard_under_mutation(shape: MutationShape) -> str:
    """Run `shape`'s guard node in a subprocess with the mutation applied; return the output.

    `-o addopts=` neutralizes the default `-m "not bite_proof"` deselect (and anything else
    `addopts` grows later, such as `--cov`) so the child run is reproducible and does not
    write a competing coverage file. `-p no:cacheprovider` leaves nothing in
    `.pytest_cache`. Neither guard node is itself marked `bite_proof`, so the neutralization
    is defensive rather than presently load-bearing.
    """
    env = {**os.environ, "VELOLOG_MUTATION": shape.name}
    result = subprocess.run(  # noqa: S603
        [
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
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout + result.stderr


@pytest.mark.bite_proof
@pytest.mark.parametrize("shape", MUTATION_SHAPES, ids=lambda s: s.name)
def test_the_mutation_shape_flips_its_guard_for_the_named_reason(shape: MutationShape) -> None:
    output = _run_guard_under_mutation(shape)

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

    assert shape.fragment in output, (
        f"shape {shape.name!r}'s guard failed, but not for the named reason — the expected "
        f"fragment {shape.fragment!r} is absent from the output, which means either the "
        f"guard was weakened (a different assertion in it failed first) or the patch target "
        f"moved:\n{output}"
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
    """(relative path, test name) for every `test_*` function under `tests/`.

    Reuses Phase 2's AST parse — `_module_test_functions` is the same function
    `tests/test_assertion_strength.py::_collect_analysis` uses to split a module's top-level
    defs into tests and helpers — rather than `pytest --collect-only`, which would run a
    whole-suite collection pass inside the default suite: exactly the cost the `bite_proof`
    marker and `addopts` exist to keep out of the local edit loop.
    """
    names: set[tuple[str, str]] = set()
    for path in sorted(TEST_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(REPO_ROOT).as_posix()
        test_fns, _helper_fns = _module_test_functions(tree)
        names.update((relative, fn.name) for fn in test_fns)
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
