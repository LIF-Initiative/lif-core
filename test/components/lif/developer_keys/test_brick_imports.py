"""The developer_keys brick must not import the MDR domain (#1180).

The control plane (#1041) packages this brick. An import from any ``lif.mdr_*`` brick would make
it inherit the MDR domain, which is what the extraction exists to prevent.
"""

import ast
from pathlib import Path

# Located by path, not by importing the brick, so a forbidden import that fails at import time
# still reaches the assertion below instead of erroring at collection.
BRICK_DIR = Path(__file__).resolve().parents[4] / "components" / "lif" / "developer_keys"


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_brick_imports_nothing_from_the_mdr_domain():
    sources = sorted(BRICK_DIR.glob("*.py"))
    assert len(sources) >= 4  # __init__, core, dto, models: guards against scanning an empty dir

    offending = [
        f"{path.name}: {module}"
        for path in sources
        for module in _imported_modules(path)
        if module.startswith("lif.mdr_")
    ]
    assert offending == []
