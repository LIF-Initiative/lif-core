"""The developer_keys brick must not import the MDR domain (#1180).

The control plane (#1041) packages this brick. An import from any ``lif.mdr_*`` brick would make
it inherit the MDR domain, which is what the extraction exists to prevent.
"""

import ast
from pathlib import Path

import pytest

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
            # `from lif import mdr_services` names the brick in the alias, not the module.
            if node.module == "lif":
                modules.extend(f"lif.{alias.name}" for alias in node.names)
    return modules


def _mdr_imports(path: Path) -> list[str]:
    return [module for module in _imported_modules(path) if module.startswith("lif.mdr_")]


def test_brick_imports_nothing_from_the_mdr_domain():
    sources = sorted(BRICK_DIR.glob("*.py"))
    assert len(sources) >= 4  # __init__, core, dto, models: guards against scanning an empty dir

    offending = [f"{path.name}: {module}" for path in sources for module in _mdr_imports(path)]
    assert offending == []


@pytest.mark.parametrize(
    "source",
    [
        "import lif.mdr_utils",
        "from lif.mdr_utils.database_setup import get_session",
        "from lif import mdr_services",
        "from lif import developer_keys, mdr_services",
    ],
)
def test_guard_catches_each_import_form(tmp_path, source):
    path = tmp_path / "module.py"
    path.write_text(source + "\n")
    assert _mdr_imports(path) != []


def test_guard_allows_non_mdr_lif_imports(tmp_path):
    path = tmp_path / "module.py"
    path.write_text("from lif import developer_keys\nimport lif.logging\n")
    assert _mdr_imports(path) == []
