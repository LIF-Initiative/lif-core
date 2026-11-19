"""Reference checks for the MongoDB seed data in ``projects/mongodb/sample_data``.

A reference finds its organization by exact identifier within the same file.
Nothing at runtime checks that — the loader imports records as they are — so a
reference to an identifier the file doesn't contain goes unnoticed (see #1526).
"""

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

SAMPLE_DATA = Path(__file__).resolve().parents[2] / "projects" / "mongodb" / "sample_data"
# Folders of deliberately flawed records (#1525): some of their references are broken on purpose.
DELIBERATELY_FLAWED = {"dev-single-org-degraded"}
SAMPLE_FILES = sorted(p for p in SAMPLE_DATA.glob("*/*.json") if p.parent.name not in DELIBERATELY_FLAWED)


def _organization_references(node: Any) -> Iterator[dict[str, Any]]:
    """Yield every object stored under a ``...RefOrganization`` key."""
    if isinstance(node, dict):
        for key, value in node.items():
            if "RefOrganization" in key:
                for ref in value if isinstance(value, list) else [value]:
                    if isinstance(ref, dict) and "identifier" in ref:
                        yield ref
            yield from _organization_references(value)
    elif isinstance(node, list):
        for item in node:
            yield from _organization_references(item)


def test_sample_files_are_found():
    assert SAMPLE_FILES


@pytest.mark.parametrize("sample_file", SAMPLE_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_organization_references_resolve_within_the_file(sample_file: Path):
    with sample_file.open(encoding="utf-8") as f:
        record = json.load(f)

    organizations = {org["identifier"] for org in record.get("Organization", [])}
    unresolved = sorted(
        {ref["identifier"] for ref in _organization_references(record) if ref["identifier"] not in organizations}
    )

    assert unresolved == []
