#!/usr/bin/env python3
"""Fail if a deploy workflow's `paths:` filter does not cover the bricks its project packages.

Each `.github/workflows/lif_*.yml` gates its `push: main` trigger on a hand-written
`paths:` list. That list duplicates dependency information which already exists,
precisely, in the project's `pyproject.toml` under `[tool.polylith.bricks]`. Any
duplicated list drifts, and when it does a change confined to an un-watched brick
merges green and never rebuilds the image -- the service keeps running the old code
with nothing reporting it (#1171).

This re-derives the brick set from `pyproject.toml` and checks the filter covers it,
so the drift is a red PR rather than a silent non-deploy.

Usage:
    python3 scripts/check-workflow-paths.py          # check, exit 1 on drift
    python3 scripts/check-workflow-paths.py --list   # print the coverage table
"""

from __future__ import annotations

import pathlib
import re
import sys
import tomllib

REPO = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO / ".github" / "workflows"

# A workflow whose deploy is genuinely not brick-derived can opt out here, with a
# reason. Keep this empty unless there is one -- an entry is a standing exception,
# not a way to silence a real gap.
EXEMPT: dict[str, str] = {}


def workflow_paths(text: str) -> list[str]:
    """The `paths:` entries under the workflow's push trigger."""
    match = re.search(r"^\s*paths:\s*\n((?:\s*-\s*.+\n)+)", text, re.M)
    return re.findall(r"-\s*(\S+)", match.group(1)) if match else []


def project_bricks(project: str) -> list[str]:
    """Repo-relative paths of the bricks a project packages."""
    pyproject = REPO / "projects" / project / "pyproject.toml"
    if not pyproject.exists():
        return []
    data = tomllib.loads(pyproject.read_text())
    bricks = (data.get("tool", {}).get("polylith", {}) or {}).get("bricks", {}) or {}
    return [re.sub(r"^(\.\./)+", "", key) for key in bricks]


def covered(brick: str, paths: list[str]) -> bool:
    """True when some `paths:` glob would match a change inside `brick`."""
    for path in paths:
        prefix = path.rstrip("*").rstrip("/")
        if brick.startswith(prefix) or prefix.startswith(brick):
            return True
    return False


def audit() -> list[tuple[str, str, int, list[str]]]:
    rows = []
    for workflow in sorted(WORKFLOW_DIR.glob("lif_*.yml")):
        text = workflow.read_text()
        project_match = re.search(r"projects/([a-z0-9_]+)", text)
        if not project_match:
            continue
        project = project_match.group(1)
        bricks = project_bricks(project)
        if not bricks:
            continue
        paths = workflow_paths(text)
        missing = [brick for brick in bricks if not covered(brick, paths)]
        rows.append((workflow.name, project, len(bricks), missing))
    return rows


def main() -> int:
    rows = audit()
    if not rows:
        print("check-workflow-paths: no deploy workflows found -- has the layout changed?")
        return 1

    show_all = "--list" in sys.argv
    failures = 0
    for name, _project, brick_count, missing in rows:
        if name in EXEMPT:
            if show_all:
                print(f"  {name:46s} {brick_count:3d} bricks  EXEMPT ({EXEMPT[name]})")
            continue
        if missing:
            failures += 1
            print(f"  {name:46s} {brick_count:3d} bricks  MISSING {len(missing)}:")
            for brick in missing:
                print(f"      {brick}")
        elif show_all:
            print(f"  {name:46s} {brick_count:3d} bricks  ok")

    if failures:
        print(
            f"\n{failures} of {len(rows)} deploy workflows do not watch every brick their project packages.\n"
            "A change confined to one of the bricks above merges green and never rebuilds that\n"
            "service's image. Add the brick to that workflow's `paths:` filter (#1171)."
        )
        return 1

    print(f"check-workflow-paths: {len(rows)} deploy workflows cover every packaged brick.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
