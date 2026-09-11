"""ADR 0004 rule 4: core components must never depend on demo bricks.

Demo bricks may depend on core components; the reverse is what breaks standalone
adoption, so it is the direction worth guarding. `poly check` does not enforce this —
it only validates that the bricks a project uses are declared — so we check it here.

Scope and limits. This reads static `import` / `from ... import` statements under
`components/lif`, which covers every form the codebase actually uses. It does not see a
dynamic `importlib.import_module("lif.demo_x")` or `__import__`, because the module name is
then a runtime string rather than an AST node. Catching those would mean matching on string
literals, which cannot distinguish a real import from a mention in a docstring or a test.
Nothing in the tree does that today; if a brick ever needs to, it should register itself with
core at startup instead — the inversion this ADR is asking for anyway.

See docs/design/adr/general/0004-components-are-the-unit-of-reuse.md
"""

import ast
from pathlib import Path
from textwrap import dedent

DEMO_BRICK_PREFIX = "demo_"
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS_DIR = REPO_ROOT / "components"
NAMESPACE = "lif"

# Where an adapter id can actually be resolved at runtime. `data_source_adapters/__init__.py`
# is excluded because it *defines* the lookups rather than consuming them.
ADAPTER_LOOKUPS = ("get_adapter_by_id", "get_adapter_class_by_id")
LOOKUP_DEFINITION = COMPONENTS_DIR / NAMESPACE / "data_source_adapters" / "__init__.py"
SEARCH_ROOTS = ("components", "bases", "orchestrators", "projects")


def _module_name(path: Path) -> str:
    """`components/lif/foo/bar.py` -> `lif.foo.bar` (dropping a trailing `__init__`)."""
    parts = path.relative_to(COMPONENTS_DIR).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(tree: ast.AST, package: str) -> list[str]:
    """Absolute module names imported by `tree`, resolving relative imports against `package`.

    For `from X import a, b` this yields `X` *and* `X.a`, `X.b`. Both halves are needed: a
    brick is most naturally imported as `from lif import demo_thing`, where the demo brick
    appears only in `node.names` and `node.module` is the bare namespace `lif`. Reading the
    module alone let that form -- and its relative twin `from .. import demo_thing` -- straight
    through the guard.

    Emitting `X.a` for a plain attribute (`from lif.foo.core import Bar` -> `lif.foo.core.Bar`)
    is harmless here, because `_is_demo_module` only ever looks at the first two segments.
    """
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                # `from ..sibling import x` inside a brick still resolves to `lif.sibling`.
                # level 1 is the current package, level 2 its parent, and so on.
                parts = package.split(".")
                prefix = ".".join(parts[: len(parts) - (node.level - 1)])
                base = f"{prefix}.{node.module}" if node.module else prefix
            if base:
                imported.append(base)
                imported.extend(f"{base}.{alias.name}" for alias in node.names)
    return imported


def _is_demo_module(module: str) -> bool:
    parts = module.split(".")
    return len(parts) >= 2 and parts[0] == NAMESPACE and parts[1].startswith(DEMO_BRICK_PREFIX)


def _core_component_files() -> list[Path]:
    """Every .py under components/lif that is not itself part of a demo brick."""
    return [
        path
        for path in sorted((COMPONENTS_DIR / NAMESPACE).rglob("*.py"))
        if not path.relative_to(COMPONENTS_DIR / NAMESPACE).parts[0].startswith(DEMO_BRICK_PREFIX)
    ]


def test_no_core_component_imports_a_demo_brick():
    violations = []
    for path in _core_component_files():
        package = _module_name(path).rsplit(".", 1)[0] if path.name != "__init__.py" else _module_name(path)
        tree = ast.parse(path.read_text(), filename=str(path))
        violations.extend(
            f"{path.relative_to(COMPONENTS_DIR.parent)} imports {module}"
            for module in _imported_modules(tree, package)
            if _is_demo_module(module)
        )

    assert not violations, (
        "Core components must not depend on demo bricks (ADR 0004 rule 4). "
        "Move the shared logic into a core component, or invert the dependency so the "
        "demo brick registers itself with core at startup:\n  " + "\n  ".join(violations)
    )


def test_the_guard_actually_sees_the_component_tree():
    """A typo in the glob would make the test above vacuously pass."""
    files = _core_component_files()
    assert len(files) > 50, f"expected the full component tree, found {len(files)} files"
    assert any(_module_name(p).startswith("lif.data_source_adapters") for p in files)
    assert not any(_module_name(p).startswith("lif.demo_") for p in files)


def test_bare_namespace_import_forms_are_caught():
    """The two forms that bypassed this guard before `node.names` was walked.

    `from lif import demo_x` and `from .. import demo_x` both put the brick name in
    `node.names` while `node.module` is the bare namespace (or None), so a check that read
    only the module saw `lif` -- one segment, never a demo match. Verified bypassing: with
    either line planted in `components/lif/data_source_adapters/__init__.py`, the guard still
    reported 3 passed.
    """
    absolute = _imported_modules(ast.parse("from lif import demo_data_source_adapters"), "lif.data_source_adapters")
    assert "lif.demo_data_source_adapters" in absolute
    assert [m for m in absolute if _is_demo_module(m)] == ["lif.demo_data_source_adapters"]

    # inside components/lif/data_source_adapters/__init__.py, package is lif.data_source_adapters
    relative = _imported_modules(ast.parse("from .. import demo_data_source_adapters"), "lif.data_source_adapters")
    assert "lif.demo_data_source_adapters" in relative
    assert [m for m in relative if _is_demo_module(m)] == ["lif.demo_data_source_adapters"]

    # multiple names on one line: the demo brick must be found alongside innocent siblings
    mixed = _imported_modules(
        ast.parse("from lif import datatypes, demo_data_source_adapters, logging"), "lif.composer"
    )
    assert [m for m in mixed if _is_demo_module(m)] == ["lif.demo_data_source_adapters"]


def test_attribute_imports_do_not_produce_false_positives():
    """`from X import SomeClass` yields `X.SomeClass`, which must not look like a brick."""
    for source in (
        "from lif.data_source_adapters.core import LIFDataSourceAdapter",
        "from lif.data_source_adapters import register_adapter",
        "from .core import LIFDataSourceAdapter",
        "from . import demo_thing",  # a submodule *inside* a brick, not a demo brick
    ):
        modules = _imported_modules(ast.parse(source), "lif.data_source_adapters")
        assert not any(_is_demo_module(m) for m in modules), f"{source} -> {modules}"


def test_relative_imports_resolve_to_the_right_brick():
    """`from ..x import y` must resolve to a sibling brick, not be silently skipped."""
    source = dedent("""
        from ..demo_thing import a
        from .core import b
    """)

    # inside lif/some_brick/sub/mod.py, package is lif.some_brick.sub.
    # Each `from X import a` contributes both X and X.a -- see _imported_modules.
    assert _imported_modules(ast.parse(source), "lif.some_brick.sub") == [
        "lif.some_brick.demo_thing",
        "lif.some_brick.demo_thing.a",
        "lif.some_brick.sub.core",
        "lif.some_brick.sub.core.b",
    ]

    # inside lif/some_brick/__init__.py, package is lif.some_brick
    assert _imported_modules(ast.parse("from ..demo_thing import a"), "lif.some_brick") == [
        "lif.demo_thing",
        "lif.demo_thing.a",
    ]
    assert _is_demo_module("lif.demo_thing")
    assert not _is_demo_module("lif.some_brick.demo_thing")


def _production_py_files() -> list[Path]:
    """Every .py under the roots where product code lives, skipping caches and venvs."""
    files = []
    for root in SEARCH_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            parts = set(path.parts)
            if "__pycache__" in parts or ".venv" in parts or "tests" in parts or "test" in parts:
                continue
            files.append(path)
    return files


def _calls_at_module_scope(tree: ast.Module) -> set[str]:
    return {
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
    }


def _imports_name(tree: ast.Module, name: str) -> bool:
    """Whether `name` is pulled in by a `from ... import name`, under its own name or an alias."""
    return any(
        isinstance(node, ast.ImportFrom) and any(alias.name == name for alias in node.names) for node in ast.walk(tree)
    )


def test_every_adapter_id_consumer_registers_the_demo_adapters():
    """The other half of the inversion — and nothing else covers it.

    Extracting the example adapter means core no longer imports it, so whoever resolves an
    adapter id has to register the demo adapters first or the lookup raises `Unknown
    adapter_id`. Today the only consumer is the Dagster job, which calls
    `register_demo_adapters()` at module scope above both of its lookups — so "forgot to
    register" is structurally impossible rather than merely handled. This pins that, and
    extends it to any future consumer.

    Checked statically because the consumer is not importable from this venv (it lives under
    `orchestrators/.../src`, outside the polylith tree) and its own `tests/test_definitions.py`
    never runs: root `testpaths = ["test"]`, and `pr-ci.yml` runs `uv run pytest test`. Without
    this test, deleting that one registration line would break every demo orchestration with
    nothing red anywhere.
    """
    consumers = []
    for path in _production_py_files():
        if path == LOOKUP_DEFINITION:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ADAPTER_LOOKUPS
        }
        if names:
            consumers.append((path, tree, sorted(names)))

    assert consumers, (
        "found no module calling get_adapter_by_id/get_adapter_class_by_id — either the search "
        "roots are wrong or the lookups were renamed, and this test has stopped checking anything"
    )

    violations = []
    for path, tree, names in consumers:
        where = f"{path.relative_to(REPO_ROOT)} calls {', '.join(names)}"
        # Both halves: the call is what registers, the import is what makes the call resolve.
        # A call without the import is a NameError at import time -- loud, but this test would
        # otherwise claim to cover a registration that cannot run.
        if "register_demo_adapters" not in _calls_at_module_scope(tree):
            violations.append(f"{where} but never calls register_demo_adapters() at module scope")
        elif not _imports_name(tree, "register_demo_adapters"):
            violations.append(f"{where} and calls register_demo_adapters() without importing it")

    assert not violations, (
        "Core no longer imports the example adapter, so every module that resolves an adapter "
        "id must register the demo adapters first (ADR 0004 rule 4 — invert the dependency and "
        "let the demo brick register itself with core at startup):\n  " + "\n  ".join(violations)
    )
