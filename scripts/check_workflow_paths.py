#!/usr/bin/env python3
"""Fail when a deploy workflow's `paths:` filter does not cover every brick its project packages.

Each deploy workflow gates its `push: main` trigger on a hand-written `paths:` list.
That list duplicates dependency information which already exists, precisely, in the
project's `pyproject.toml` under `[tool.polylith.bricks]`. Any duplicated list drifts,
and when it does a change confined to an un-watched brick merges green and never
rebuilds the image -- the service keeps running the old code with nothing reporting
it (#1171).

Coverage is directional. A filter entry covers a brick only when it sits AT or ABOVE
the brick:

    components/lif/datatypes/**        covers  components/lif/datatypes      yes
    components/**                      covers  components/lif/datatypes      yes
    components/lif/datatypes/mdr_x     covers  components/lif/datatypes      NO

The third case is the one that matters: a filter naming something *narrower* than the
brick watches only part of it, which is a gap rather than coverage. An earlier version
of this script treated the relationship as symmetric and so reported two real gaps as
covered.

A workflow that cannot be audited is reported, never skipped. Silently dropping one
would let a project rename disable the check while the summary still claimed full
coverage -- drift disabling the drift detector.

Usage:
    uv run python scripts/check_workflow_paths.py          # check, exit 1 on drift
    uv run python scripts/check_workflow_paths.py --list   # print the coverage table
"""

from __future__ import annotations

import pathlib
import re
import sys
import tomllib

REPO = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO / ".github" / "workflows"

# Workflows that deploy a project. Matched by content (they name a `projects/<name>`
# directory) rather than by filename, so a new deploy workflow is audited whatever it
# is called -- the `lif_*.yml` glob this used to apply missed both Dagster workflows.
NOT_DEPLOY_WORKFLOWS = {"pr-ci.yml", "synthetic-e2e.yml", "_deploy-service.yml"}

# Projects that build a Docker image from static assets and package no bricks, so there
# is nothing for a `paths:` filter to drift from. Named explicitly rather than inferred
# from a missing pyproject.toml, so that a project losing its pyproject.toml by accident
# is still reported as unauditable.
NO_BRICK_PROJECTS = {"mongodb", "lif_mdr_database"}


def workflow_paths(text: str) -> list[str]:
    """The `paths:` entries under the workflow's push trigger."""
    match = re.search(r"^\s*paths:\s*\n((?:\s*-\s*.+\n)+)", text, re.M)
    return re.findall(r"-\s*(\S+)", match.group(1)) if match else []


def project_bricks(project: str) -> list[str] | None:
    """Repo-relative brick paths for a project, or None when it cannot be read."""
    pyproject = REPO / "projects" / project / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text())
    bricks = (data.get("tool", {}).get("polylith", {}) or {}).get("bricks", {}) or {}
    return [re.sub(r"^(\.\./)+", "", key) for key in bricks]


def covered(brick: str, paths: list[str]) -> bool:
    """True when some `paths:` entry sits at or above `brick`."""
    for path in paths:
        prefix = path.rstrip("*").rstrip("/")
        if brick == prefix or brick.startswith(prefix + "/"):
            return True
    return False


def audit() -> tuple[list[tuple[str, str, list[str], list[str]]], list[tuple[str, str]], list[str]]:
    """Return (rows, unauditable, not_projects). rows are (workflow, project, bricks, missing)."""
    rows: list[tuple[str, str, list[str], list[str]]] = []
    unauditable: list[tuple[str, str]] = []
    not_projects: list[str] = []

    for workflow in sorted(WORKFLOW_DIR.glob("*.yml")):
        if workflow.name in NOT_DEPLOY_WORKFLOWS:
            continue
        text = workflow.read_text()
        projects = sorted(set(re.findall(r"projects/([a-z0-9_]+)", text)))
        if not projects:
            # Deploys something that is not a Polylith project -- the frontends build
            # from frontends/, not projects/. Recorded rather than dropped: the two
            # skips above are explicit named lists, but this one is a heuristic, and a
            # heuristic that silently removes a workflow from the denominator is how a
            # drift check stops seeing the thing it checks.
            not_projects.append(workflow.name)
            continue
        for project in projects:
            if project in NO_BRICK_PROJECTS:
                continue
            bricks = project_bricks(project)
            if bricks is None:
                unauditable.append((workflow.name, f"projects/{project}/pyproject.toml not found"))
                continue
            if not bricks:
                unauditable.append((workflow.name, f"projects/{project} declares no [tool.polylith.bricks]"))
                continue
            rows.append((workflow.name, project, bricks, [b for b in bricks if not covered(b, workflow_paths(text))]))
    return rows, unauditable, not_projects


def main() -> int:
    rows, unauditable, not_projects = audit()
    if not rows:
        print("check_workflow_paths: no deploy workflows found -- has the layout changed?")
        return 1

    show_all = "--list" in sys.argv
    failures = 0

    for name, project, bricks, missing in rows:
        if missing:
            failures += 1
            print(f"  {name:46s} {project:34s} MISSING {len(missing)} of {len(bricks)}:")
            for brick in missing:
                print(f"      {brick}")
        elif show_all:
            print(f"  {name:46s} {project:34s} ok ({len(bricks)} bricks)")

    if show_all and not_projects:
        print(f"  (not Polylith project deploys, so nothing to check: {', '.join(not_projects)})")

    for name, reason in unauditable:
        failures += 1
        print(f"  {name:46s} CANNOT AUDIT: {reason}")

    if failures:
        print(
            f"\n{failures} problem(s) across {len(rows)} audited deploy workflow(s).\n"
            "A change confined to an un-watched brick merges green and never rebuilds that\n"
            "service's image. Add the brick to that workflow's `paths:` filter (#1171)."
        )
        return 1

    print(f"check_workflow_paths: {len(rows)} deploy workflows cover every packaged brick.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
