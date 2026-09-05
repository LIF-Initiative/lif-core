"""ADR 0004 rule 4: core components must never depend on demo bricks.

Demo bricks may depend on core components; the reverse is what breaks standalone
adoption, so it is the direction worth guarding. `poly check` does not enforce this —
it only validates that the bricks a project uses are declared — so we check it here.

See docs/design/adr/general/0004-components-are-the-unit-of-reuse.md
"""

import ast
from pathlib import Path
from textwrap import dedent

DEMO_BRICK_PREFIX = "demo_"
COMPONENTS_DIR = Path(__file__).resolve().parents[2] / "components"
NAMESPACE = "lif"


def _module_name(path: Path) -> str:
    """`components/lif/foo/bar.py` -> `lif.foo.bar` (dropping a trailing `__init__`)."""
    parts = path.relative_to(COMPONENTS_DIR).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(tree: ast.AST, package: str) -> list[str]:
    """Absolute module names imported by `tree`, resolving relative imports against `package`."""
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imported.append(node.module)
                continue
            # `from ..sibling import x` inside a brick still resolves to `lif.sibling`.
            # level 1 is the current package, level 2 its parent, and so on.
            parts = package.split(".")
            base = parts[: len(parts) - (node.level - 1)]
            prefix = ".".join(base)
            imported.append(f"{prefix}.{node.module}" if node.module else prefix)
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


def test_relative_imports_resolve_to_the_right_brick():
    """`from ..x import y` must resolve to a sibling brick, not be silently skipped."""
    source = dedent("""
        from ..demo_thing import a
        from .core import b
    """)

    # inside lif/some_brick/sub/mod.py, package is lif.some_brick.sub
    assert _imported_modules(ast.parse(source), "lif.some_brick.sub") == [
        "lif.some_brick.demo_thing",
        "lif.some_brick.sub.core",
    ]

    # inside lif/some_brick/__init__.py, package is lif.some_brick
    assert _imported_modules(ast.parse("from ..demo_thing import a"), "lif.some_brick") == ["lif.demo_thing"]
    assert _is_demo_module("lif.demo_thing")
    assert not _is_demo_module("lif.some_brick.demo_thing")
