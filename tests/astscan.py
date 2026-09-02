"""Shared AST scanning primitives for the meta-tests under `tests/`.

`tests/test_assertion_strength.py`'s audit and `tests/test_suite_bites.py`'s bite-proof
harness both need to enumerate the test functions and methods defined under `tests/` without
paying for a `pytest --collect-only` pass. This is the one place that enumeration is built,
so what counts as a test — top-level `test_*` function or `test_*` method of a `Test*`
class — is defined once and shared, rather than each meta-test's inventory silently
diverging from the other's.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_DIR = REPO_ROOT / "tests"

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef


def module_test_functions(tree: ast.Module) -> tuple[list[FuncDef], list[FuncDef]]:
    """Split a module's top-level defs into (`test_*` functions, everything else)."""
    tests: list[FuncDef] = []
    helpers: list[FuncDef] = []
    for node in tree.body:
        if not isinstance(node, FuncDef):
            continue
        (tests if node.name.startswith("test_") else helpers).append(node)
    return tests, helpers


def class_test_methods(tree: ast.Module) -> list[tuple[str, FuncDef]]:
    """`(qualified name, method)` for every `test_*` method of a top-level `Test*` class.

    Pytest's default collection (`python_classes = Test*`, left unconfigured in
    `pyproject.toml`) only picks up classes named this way, so restricting to that prefix
    matches what pytest would actually run rather than over-counting.
    """
    methods: list[tuple[str, FuncDef]] = []
    for node in tree.body:
        if not (isinstance(node, ast.ClassDef) and node.name.startswith("Test")):
            continue
        for child in node.body:
            if isinstance(child, FuncDef) and child.name.startswith("test_"):
                methods.append((f"{node.name}::{child.name}", child))
    return methods
