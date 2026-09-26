#!/usr/bin/env python3
"""Fail if any per-project `uv.lock` is out of date with its `pyproject.toml`.

`pr-ci.yml` runs `uv sync --frozen` against the ROOT lock only. The per-project
locks under `projects/*/` are what the Docker images install from, and nothing
checked them. A dependency added to a project's `pyproject.toml` without
re-running `uv lock` therefore merges green and crash-loops the service at
startup with `ModuleNotFoundError` (#1125, and nearly again in #1174).

`uv export --frozen` is not a substitute: it exits 0 on a stale lock and simply
omits the undeclared dependency, which is the trap that let #1174 through review
once already.

Usage:
    python3 scripts/check-project-locks.py          # check, exit 1 on staleness
    python3 scripts/check-project-locks.py --list   # print every project's status

Note on uv versions: run this with the same uv the CI workflow pins
(`.github/workflows/pr-ci.yml`). Different uv versions can resolve differently,
so a lock regenerated locally with a newer uv may not satisfy the pinned one.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
PROJECTS = REPO / "projects"

# Projects whose image installs no Python dependencies, so a lock would have nothing
# to pin. Named explicitly: a project that stops installing deps by accident should
# still be reported rather than silently qualifying.
NO_PYTHON_PROJECTS = {"lif_identity_mapper_mariadb", "mongodb", "lif_mdr_database"}


def uv_version() -> str:
    try:
        out = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def check(project: pathlib.Path) -> tuple[bool, str]:
    """True when the project's lock is current. Second item is uv's message on failure.

    Subprocess failures are reported in this script's own voice rather than as a
    traceback -- a reviewer running it without uv on PATH is the likely victim.
    """
    try:
        result = subprocess.run(["uv", "lock", "--check"], cwd=project, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        return False, "uv is not on PATH"
    except subprocess.TimeoutExpired:
        return False, "uv lock --check timed out after 300s"
    except OSError as exc:  # pragma: no cover - environment-specific
        return False, f"could not run uv: {exc}"
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def lockless_projects() -> list[pathlib.Path]:
    """Projects declaring a pyproject.toml with no sibling lock.

    Globbing `*/uv.lock` alone makes these invisible rather than failing: the only
    signal is the trailing count quietly dropping, which nobody diffs. Reporting them
    keeps the denominator honest -- real coverage was 11 of 15, not 11 of 11.
    """
    return sorted(
        p.parent
        for p in PROJECTS.glob("*/pyproject.toml")
        if not (p.parent / "uv.lock").exists() and p.parent.name not in NO_PYTHON_PROJECTS
    )


def main() -> int:
    locked = sorted(p.parent for p in PROJECTS.glob("*/uv.lock"))
    if not locked:
        print("check-project-locks: no per-project uv.lock files found -- has the layout changed?")
        return 1

    show_all = "--list" in sys.argv
    stale = []
    for project in locked:
        ok, message = check(project)
        if ok:
            if show_all:
                print(f"  {project.name:38s} ok")
        else:
            stale.append(project)
            print(f"  {project.name:38s} STALE")
            for line in message.splitlines():
                if line.strip() and not line.startswith("Using CPython"):
                    print(f"      {line.strip()}")

    missing = lockless_projects()
    for project in missing:
        # A warning, not a failure. These predate this check and their images resolve
        # dependencies at build time instead; making them reproducible means generating
        # locks, which is its own change. Reported so the denominator stays honest.
        print(f"  {project.name:38s} NO LOCKFILE (build resolves fresh; not reproducible)")
        print(f"::warning file=projects/{project.name}/pyproject.toml::no uv.lock -- image deps are unpinned")

    if stale:
        for project in stale:
            print(f"::error file=projects/{project.name}/uv.lock::lockfile is out of date with pyproject.toml")
        print(
            f"\n{len(stale)} of {len(locked)} project lockfiles are out of date with their pyproject.toml.\n"
            "The Docker image installs from the lock, so a dependency declared but not locked is\n"
            "absent at runtime and the service crash-loops on import (#1125). Regenerate with:\n"
        )
        for project in stale:
            print(f"    (cd projects/{project.name} && uv lock)")
        print(f"\nUse the uv version CI pins, not whatever is on PATH. This ran {uv_version()}.")
        return 1

    print(f"check_project_locks: {len(locked)} lockfiles current, {len(missing)} project(s) unlocked ({uv_version()}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
