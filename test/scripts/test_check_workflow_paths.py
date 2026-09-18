"""Tests for the deploy-workflow paths guard (#1171).

The predicate is the part that can be silently wrong, and was: an earlier version
treated coverage as symmetric, so a filter naming something *narrower* than a brick
counted as covering it. That reported two real gaps as clean. These pin the direction.
"""

import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_workflow_paths.py"
_spec = importlib.util.spec_from_file_location("check_workflow_paths", _SCRIPT)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


@pytest.mark.parametrize(
    "brick,paths,expected,why",
    [
        ("components/lif/datatypes", ["components/lif/datatypes/**"], True, "exact brick with glob"),
        ("components/lif/datatypes", ["components/lif/datatypes"], True, "exact brick, no glob"),
        ("components/lif/datatypes", ["components/**"], True, "broader ancestor covers"),
        ("bases/lif/mdr_restapi", ["bases/lif/mdr_restapi/**"], True, "bases bricks work the same"),
        # The three that the symmetric predicate got wrong:
        (
            "components/lif/datatypes",
            ["components/lif/datatypes/mdr_sqlmodel"],
            False,
            "a path narrower than the brick is a gap, not coverage",
        ),
        (
            "components/lif/identity_mapper_storage",
            ["components/lif/identity_mapper_storage_sql/**"],
            False,
            "a sibling brick sharing a string prefix does not cover",
        ),
        ("components/lif/foo", ["components/lif/foobar/**"], False, "string-prefix siblings must not match"),
    ],
)
def test_coverage_is_directional(brick, paths, expected, why):
    assert guard.covered(brick, paths) is expected, why


def test_repo_workflows_all_cover_their_bricks():
    """The live audit passes. This is the regression guard for the repo itself."""
    rows, unauditable = guard.audit()
    assert rows, "no deploy workflows discovered -- has the layout changed?"
    drifted = {name: missing for name, _project, _bricks, missing in rows if missing}
    assert not drifted, f"workflows missing brick coverage: {drifted}"
    assert not unauditable, f"workflows that could not be audited: {unauditable}"


def test_dagster_workflows_are_audited():
    """They were invisible while the script globbed lif_*.yml, and had a real gap."""
    audited = {name for name, _p, _b, _m in guard.audit()[0]}
    assert "dagster_code_location.yml" in audited
    assert "dagster.yml" in audited


def test_an_unreadable_project_is_reported_not_skipped(monkeypatch):
    """Dropping a workflow silently would let drift disable the drift detector."""
    monkeypatch.setattr(guard, "project_bricks", lambda project: None)
    monkeypatch.setattr(guard, "NO_BRICK_PROJECTS", set())
    rows, unauditable = guard.audit()
    assert not rows
    assert unauditable, "an unreadable project must surface, not vanish from the denominator"
