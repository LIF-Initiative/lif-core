"""Projects that ship SQLAlchemy's asyncio API must declare sqlalchemy[asyncio].

SQLAlchemy 2.1 stopped installing greenlet by default. Dockerfile2 re-resolves
dependencies from the wheel's metadata, not uv.lock, so a project that imports
sqlalchemy.ext.asyncio without the extra builds an image that crashes on import.
"""

import importlib.util
import pathlib
import re
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

ASYNC_IMPORT = re.compile(r"^\s*(from|import)\s+sqlalchemy\.ext\.asyncio\b", re.M)
# Images like lif_identity_mapper_mariadb list bricks but install no Python, so they can't crash.
PROJECTS = sorted(
    p.parent.name for p in REPO.glob("projects/*/pyproject.toml") if p.parent.name not in locks.NO_PYTHON_PROJECTS
)


def uses_sqlalchemy_asyncio(bricks: list[str]) -> list[str]:
    """Packaged .py files that import sqlalchemy.ext.asyncio."""
    return [
        str(f.relative_to(REPO))
        for brick in bricks
        for f in (REPO / brick).rglob("*.py")
        if ASYNC_IMPORT.search(f.read_text())
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
            '"sqlalchemy[asyncio]" (greenlet is missing in Dockerfile2 images)'
        )


def test_detects_the_import() -> None:
    # Guard against the scan silently matching nothing: mdr_services is a known importer.
    assert uses_sqlalchemy_asyncio(["components/lif/mdr_services"])
