"""Tests for the #1350 transformation-group backfill and its asyncpg runner.

The backfill is a one-time data fix for dev and demo, so there is no second chance to find a
wrong rule. These run the SQL against a real Postgres, one fixture pair per rule, through the
Python runner and (when psql is installed) the shell script, and check both see the same changes.
The DB-backed tests skip without a local PostgreSQL (`initdb`), like the MDR tests.
"""

import importlib.util
import os
import pathlib
import shutil
import subprocess
from urllib.parse import urlparse

import asyncpg
import pytest
import testing.postgresql

_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "scripts"
_SHELL_SCRIPT = _SCRIPTS / "backfill-transformation-group-activation.sh"
_spec = importlib.util.spec_from_file_location(
    "backfill_transformation_group_activation", _SCRIPTS / "backfill_transformation_group_activation.py"
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)

_TABLE = """
CREATE TABLE {schema}."TransformationsGroup" (
    "Id" bigint PRIMARY KEY,
    "SourceDataModelId" bigint NOT NULL,
    "TargetDataModelId" bigint NOT NULL,
    "GroupVersion" text,
    "ActivationDate" timestamp with time zone,
    "DeprecationDate" timestamp with time zone,
    "Deleted" boolean DEFAULT false
)
"""

_PAST = "now() - interval '1 day'"
_FUTURE = "now() + interval '1 day'"

# (Id, source, target, version, ActivationDate, DeprecationDate), one pair per rule.
_PUBLIC_ROWS = [
    # Undated only: the highest is activated, the older ones deprecated.
    (101, 1, 2, "1.0", None, None),
    (102, 1, 2, "2.0", None, None),
    (103, 1, 2, "3.0", None, None),
    # Undated below a dated live version: deprecated, the dated one stays the only active row.
    (201, 3, 4, "1.0", None, None),
    (202, 3, 4, "2.0", _PAST, None),
    # Dated live version below an undated one: the undated one is activated, the dated one deprecated.
    (301, 5, 6, "1.0", _PAST, None),
    (302, 5, 6, "2.0", None, None),
    # Two dated live versions and nothing undated: the lower one is deprecated.
    (401, 7, 8, "1.0", _PAST, None),
    (402, 7, 8, "2.0", _PAST, None),
    # Tied undated top: the whole pair is skipped, including its dated live version.
    (501, 9, 10, "1", None, None),
    (502, 9, 10, "1.0", None, None),
    (503, 9, 10, "0.5", _PAST, None),
    # Free text: skipped.
    (601, 11, 12, "beta", None, None),
    # A scheduled version is not active, so the undated one below it is activated.
    (701, 13, 14, "1.0", None, None),
    (702, 13, 14, "2.0", _FUTURE, None),
    # Numeric, not string, order.
    (801, 15, 16, "9.0", None, None),
    (802, 15, 16, "10.0", None, None),
    # A future DeprecationDate survives activation and is flagged.
    (901, 17, 18, "2.0", None, _FUTURE),
    # An already deprecated dated version is not active and is left alone.
    (1001, 19, 20, "1.0", _PAST, _PAST),
    (1002, 19, 20, "2.0", None, None),
]
_TENANT_ROWS = [(101, 1, 2, "1.0", None, None), (102, 1, 2, "2.0", None, None)]

_EXPECTED = {
    "public": {
        (101, "deprecated"),
        (102, "deprecated"),
        (103, "activated"),
        (201, "deprecated: at or below the active version"),
        (301, "deprecated: was active, below the version the pair keeps"),
        (302, "activated"),
        (401, "deprecated: was active, below the version the pair keeps"),
        (501, "skipped: highest version is tied"),
        (502, "skipped: highest version is tied"),
        (601, "skipped: GroupVersion is not dotted integers"),
        (701, "activated"),
        (801, "deprecated"),
        (802, "activated"),
        (901, "activated: keeps its future DeprecationDate"),
        (1002, "activated"),
    },
    "tenant_a": {(101, "deprecated"), (102, "activated")},
}
# The rows active after --apply, per schema and pair.
_ACTIVE_AFTER = {"public": {103, 202, 302, 402, 503, 701, 802, 901, 1002}, "tenant_a": {102}}


def _actions(rows) -> set[tuple[int, str]]:
    # The flagged action carries a timestamp, so compare its fixed prefix.
    return {(r["group_id"], r["action"].split(" 20")[0]) for r in rows}


@pytest.fixture(scope="module")
def postgres_url():
    try:
        postgresql = testing.postgresql.Postgresql()
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    with postgresql:
        yield postgresql.url()


@pytest.fixture
async def conn(postgres_url):
    connection = await asyncpg.connect(postgres_url)
    for schema, rows in (("public", _PUBLIC_ROWS), ("tenant_a", _TENANT_ROWS)):
        await connection.execute(f'DROP TABLE IF EXISTS {schema}."TransformationsGroup"')
        await connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        await connection.execute(_TABLE.format(schema=schema))
        for row_id, source, target, version, activation, deprecation in rows:
            await connection.execute(
                f'INSERT INTO {schema}."TransformationsGroup" VALUES '
                f"($1, $2, $3, $4, {activation or 'NULL'}, {deprecation or 'NULL'})",
                row_id,
                source,
                target,
                version,
            )
    yield connection
    await connection.close()


async def _active_ids(conn, schema: str) -> set[int]:
    rows = await conn.fetch(
        f'SELECT "Id" FROM {schema}."TransformationsGroup" WHERE "Deleted" IS NOT TRUE '
        'AND "ActivationDate" <= now() AND ("DeprecationDate" IS NULL OR "DeprecationDate" > now())'
    )
    return {r["Id"] for r in rows}


def test_runner_sql_is_the_shell_scripts_sql():
    """What bjagg runs through ECS exec must be the tested text, not a hand-edited copy."""
    shell = _SHELL_SCRIPT.read_text()
    start = shell.index("    cat <<'SQL'\n") + len("    cat <<'SQL'\n")
    assert backfill.BACKFILL_SQL == shell[start : shell.index("\nSQL\n}", start)]


def test_render_quotes_the_schema_as_psql_would():
    sql = backfill.render("te\"n'ant")
    assert '"te""n\'ant"."TransformationsGroup"' in sql
    assert "SELECT 'te\"n''ant' AS schema" in sql
    assert ':"schema"' not in sql and ":'schema'" not in sql


async def test_dry_run_reports_every_rule_and_changes_nothing(conn):
    before = {s: await _active_ids(conn, s) for s in ("public", "tenant_a")}
    _, results = await backfill.backfill(conn, apply=False)
    assert list(results) == ["public", "tenant_a"]
    assert {s: _actions(rows) for s, rows in results.items()} == _EXPECTED
    assert {s: await _active_ids(conn, s) for s in ("public", "tenant_a")} == before


async def test_apply_leaves_one_active_row_per_pair_and_is_idempotent(conn):
    run_timestamp, _ = await backfill.backfill(conn, apply=True)
    assert {s: await _active_ids(conn, s) for s in ("public", "tenant_a")} == _ACTIVE_AFTER
    # Every change carries run_timestamp, which is what the undo matches on.
    changed = await conn.fetchval(
        'SELECT count(*) FROM public."TransformationsGroup" WHERE "ActivationDate" = $1 OR "DeprecationDate" = $1',
        run_timestamp,
    )
    assert changed == sum(1 for _, action in _EXPECTED["public"] if not action.startswith("skipped"))

    _, again = await backfill.backfill(conn, apply=True)
    assert all(action.startswith("skipped") for rows in again.values() for _, action in _actions(rows))


@pytest.mark.skipif(shutil.which("psql") is None, reason="psql not installed")
async def test_shell_script_reports_the_same_changes(conn, postgres_url):
    _, results = await backfill.backfill(conn, apply=False)
    parsed = urlparse(postgres_url)
    env = {
        **os.environ,
        "PGHOST": parsed.hostname or "",
        "PGPORT": str(parsed.port),
        "PGUSER": parsed.username or "",
        "PGDATABASE": parsed.path.lstrip("/"),
    }
    out = subprocess.run(["bash", str(_SHELL_SCRIPT)], env=env, capture_output=True, text=True, check=True).stdout
    shell_rows = {}
    for line in out.splitlines():
        fields = [f.strip() for f in line.split("|")]
        if len(fields) == 6 and fields[0] in ("public", "tenant_a"):
            shell_rows.setdefault(fields[0], set()).add((int(fields[3]), fields[5].split(" 20")[0]))
    assert shell_rows == {s: _actions(rows) for s, rows in results.items()}
