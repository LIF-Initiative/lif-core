"""Tests for the per-project lockfile guard (#1209).

The failure this guards against is silent: a declared dependency that never reaches
the image, so the service crash-loops at import (#1125, #1174). An earlier version of
this script had a quieter version of the same problem -- a project with no lock was
skipped rather than reported, so the coverage count dropped without anything saying so.
"""

import importlib.util
import pathlib

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_project_locks.py"
_spec = importlib.util.spec_from_file_location("check_project_locks", _SCRIPT)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def test_projects_without_a_lock_are_reported_not_skipped():
    """The denominator must be honest: real coverage is 11 of 14, not 11 of 11."""
    lockless = guard.lockless_projects()
    names = {p.name for p in lockless}
    assert names, "projects without locks exist and must be surfaced"
    # the three Dagster projects resolve deps at build time with no lock
    assert {"dagster_docker_compose", "dagster_oss_ecs", "dagster_plus_hybrid"} <= names


def test_projects_that_install_no_python_are_exempt():
    """A MariaDB or MongoDB image has nothing to pin; it must not read as a gap."""
    names = {p.name for p in guard.lockless_projects()}
    assert "lif_identity_mapper_mariadb" not in names
    assert guard.NO_PYTHON_PROJECTS, "the exemption list must be explicit, not inferred"


def test_a_missing_uv_binary_reports_rather_than_tracebacks(monkeypatch, tmp_path):
    """A reviewer running this locally without uv should get the script's message."""

    def boom(*_args, **_kwargs):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(guard.subprocess, "run", boom)
    ok, message = guard.check(tmp_path)
    assert ok is False
    assert "uv is not on PATH" in message


def test_a_timeout_reports_rather_than_tracebacks(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise guard.subprocess.TimeoutExpired(cmd="uv", timeout=300)

    monkeypatch.setattr(guard.subprocess, "run", boom)
    ok, message = guard.check(tmp_path)
    assert ok is False
    assert "timed out" in message
