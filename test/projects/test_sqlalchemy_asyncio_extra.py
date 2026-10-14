"""Projects that ship SQLAlchemy's asyncio API must declare sqlalchemy[asyncio].

sqlalchemy.ext.asyncio needs greenlet. SQLAlchemy 2.0 installs greenlet by default,
but 2.1 only installs it through the `asyncio` extra. Without the extra, the first
lock upgrade to 2.1 drops greenlet from uv.lock, and the image crashes on import.
"""

import ast
import importlib.util
import pathlib
import tomllib
from types import ModuleType

import pytest
from packaging.requirements import Requirement

REPO = pathlib.Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cwp = _load_script("check_workflow_paths")
locks = _load_script("check_project_locks")

ASYNC_MODULE = "sqlalchemy.ext.asyncio"
# Images like lif_identity_mapper_mariadb list bricks but install no Python, so they can't crash.
PROJECTS = sorted(
    p.parent.name for p in REPO.glob("projects/*/pyproject.toml") if p.parent.name not in locks.NO_PYTHON_PROJECTS
)


def imports_sqlalchemy_asyncio(source: str) -> bool:
    """True if the module imports sqlalchemy.ext.asyncio, in any import form."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(a.name.startswith(ASYNC_MODULE) for a in node.names):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (
                node.module.startswith(ASYNC_MODULE)
                or (node.module == "sqlalchemy.ext" and any(a.name == "asyncio" for a in node.names))
            )
        ):
            return True
    return False


def uses_sqlalchemy_asyncio(bricks: list[str]) -> list[str]:
    """Packaged .py files that import sqlalchemy.ext.asyncio."""
    return [
        str(f.relative_to(REPO))
        for brick in bricks
        for f in (REPO / brick).rglob("*.py")
        if imports_sqlalchemy_asyncio(f.read_text())
    ]


def declares_asyncio_extra(project: str) -> bool:
    data = tomllib.loads((REPO / "projects" / project / "pyproject.toml").read_text())
    requirements = (Requirement(d) for d in data["project"]["dependencies"])
    return any(r.name.lower() == "sqlalchemy" and "asyncio" in r.extras for r in requirements)


@pytest.mark.parametrize("project", PROJECTS)
def test_asyncio_users_declare_the_extra(project: str) -> None:
    importers = uses_sqlalchemy_asyncio(cwp.project_bricks(project, REPO) or [])
    if importers:
        assert declares_asyncio_extra(project), (
            f"projects/{project} packages {importers} but does not depend on "
            '"sqlalchemy[asyncio]" (greenlet drops out of uv.lock on SQLAlchemy 2.1)'
        )


def test_detects_the_import() -> None:
    # Guard against the scan silently matching nothing: mdr_services is a known importer.
    assert uses_sqlalchemy_asyncio(["components/lif/mdr_services"])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from sqlalchemy.ext.asyncio import AsyncSession", True),
        ("import sqlalchemy.ext.asyncio", True),
        ("import sqlalchemy.ext.asyncio as sa", True),
        ("from sqlalchemy.ext import asyncio", True),
        ("from sqlalchemy.ext import asyncio as sa_async", True),
        ("from sqlalchemy.ext import (\n    asyncio,\n)", True),
        ("from sqlalchemy.ext import declarative", False),
        ("from sqlalchemy import select", False),
        ('"""Example:\nfrom sqlalchemy.ext.asyncio import AsyncSession\n"""', False),
    ],
)
def test_import_detection(source: str, expected: bool) -> None:
    assert imports_sqlalchemy_asyncio(source) is expected
