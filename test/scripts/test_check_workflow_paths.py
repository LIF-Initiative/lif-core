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


def _make_repo(tmp_path, workflow_paths, dockerfile=None, bricks=("components/lif/foo",)):
    """A minimal repo: one project packaging `bricks`, one deploy workflow for it."""
    project = tmp_path / "projects" / "svc"
    project.mkdir(parents=True)
    brick_lines = "\n".join(f'"../../{b}" = "lif/{b.rsplit("/", 1)[1]}"' for b in bricks)
    (project / "pyproject.toml").write_text(f"[tool.polylith.bricks]\n{brick_lines}\n")
    build = ""
    if dockerfile is not None:
        name, body = dockerfile
        if body is not None:
            (project / name).write_text(body)
        build = f"      - run: docker build -f projects/svc/{name} .\n"
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    listed = "".join(f"      - {p}\n" for p in workflow_paths)
    (workflows / "svc.yml").write_text(
        f"on:\n  push:\n    paths:\n{listed}jobs:\n  deploy:\n    steps:\n{build}      - run: echo projects/svc\n"
    )
    return tmp_path


def _missing(result):
    return {name: missing for name, _project, _bricks, missing in result[0] if missing}


def test_a_covering_workflow_passes_and_a_drifted_one_is_reported(tmp_path):
    """Fixture repo, not the live one: a brick added on main must fail the guard step,
    not also every open PR's pytest (#1274 review)."""
    ok = guard.audit(_make_repo(tmp_path / "ok", ["projects/svc/**", "components/lif/foo/**"]))
    assert ok[0] and not _missing(ok)
    drifted = guard.audit(_make_repo(tmp_path / "drift", ["projects/svc/**"]))
    assert _missing(drifted) == {"svc.yml": ["components/lif/foo"]}


def test_a_named_dockerfile_that_packages_no_bricks_needs_no_brick_paths(tmp_path):
    """dagster.yml builds Dockerfile.dagster: pip install plus two YAML copies. Requiring
    the project's bricks in its filter only forces rebuilds nobody needs."""
    body = "FROM python:3.13-slim\nRUN pip install dagster\nCOPY projects/svc/dagster.yaml /opt/\n"
    rows, unauditable, _not_projects, brick_free = guard.audit(
        _make_repo(tmp_path, ["projects/svc/**"], dockerfile=("Dockerfile.web", body))
    )
    assert not rows and not unauditable
    assert brick_free == [("svc.yml", "projects/svc/Dockerfile.web")], "recorded, not silently dropped"


@pytest.mark.parametrize(
    "copy_line",
    [
        "COPY components/ /code/components/",
        "COPY bases/ /code/bases/",
        "COPY . /code",
        "COPY projects/svc/dist/*.whl /tmp/",  # a prebuilt wheel carries the bricks too
        'COPY ["components", "/code/components"]',  # a form the parser doesn't read counts as packaging
    ],
)
def test_a_named_dockerfile_that_packages_bricks_is_still_audited(tmp_path, copy_line):
    body = f"FROM python:3.13-slim\n{copy_line}\n"
    result = guard.audit(_make_repo(tmp_path, ["projects/svc/**"], dockerfile=("Dockerfile.code", body)))
    assert _missing(result) == {"svc.yml": ["components/lif/foo"]}


def test_a_named_dockerfile_that_does_not_exist_is_reported(tmp_path):
    rows, unauditable, _not_projects, _brick_free = guard.audit(
        _make_repo(tmp_path, ["projects/svc/**"], dockerfile=("Dockerfile.gone", None))
    )
    assert not rows
    assert unauditable == [("svc.yml", "projects/svc/Dockerfile.gone not found")]


def test_dagster_workflows_are_classified_by_the_image_they_build():
    """Live repo, but only its classification, which a new brick can't change. The code
    location copies bases/ and components/; the webserver/daemon image copies neither."""
    rows, _unauditable, _not_projects, brick_free = guard.audit()
    assert "dagster_code_location.yml" in {name for name, _p, _b, _m in rows}
    assert ("dagster.yml", "projects/dagster_oss_ecs/Dockerfile.dagster") in brick_free


def test_an_unreadable_project_is_reported_not_skipped(monkeypatch):
    """Dropping a workflow silently would let drift disable the drift detector."""
    monkeypatch.setattr(guard, "project_bricks", lambda project, repo: None)
    monkeypatch.setattr(guard, "NO_BRICK_PROJECTS", set())
    rows, unauditable, _not_projects, _brick_free = guard.audit()
    assert not rows
    assert unauditable, "an unreadable project must surface, not vanish from the denominator"


def test_non_project_deploys_are_recorded_not_silently_dropped():
    """The two named skips are auditable lists; this one is a heuristic.

    A heuristic that removes a workflow from the denominator without saying so is how
    a drift check quietly stops checking something.
    """
    _rows, _unauditable, not_projects, _brick_free = guard.audit()
    assert "lif_mdr_frontend.yml" in not_projects, "frontend deploys build from frontends/, not projects/"
