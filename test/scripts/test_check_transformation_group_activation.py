"""Tests for the #1350 check that each transformation group pair has exactly one active version.

The check is the gate before the Translator switches endpoints, so a pair it wrongly passes
becomes a 404 or 409 in production. The rules are tested directly; one DB-backed test covers
the schema loop and skips without a local PostgreSQL (`initdb`), like the MDR tests.
"""

import importlib.util
import pathlib
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
import testing.postgresql

_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_transformation_group_activation", _SCRIPTS / "check_transformation_group_activation.py"
)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=1)
LONG_AGO = NOW - timedelta(days=30)
FUTURE = NOW + timedelta(days=1)


def _group(group_id, version, activation=None, deprecation=None):
    return {"Id": group_id, "GroupVersion": version, "ActivationDate": activation, "DeprecationDate": deprecation}


@pytest.mark.parametrize(
    "groups, status",
    [
        # The backfill's usual result: the top version active, the older undated ones deprecated.
        ([_group(1, "1.0", None, PAST), _group(2, "2.0", PAST)], "ok"),
        ([_group(1, "1.0", PAST, FUTURE)], "ok"),
        # bjagg's two retired pairs on dev: dated and deprecated, before or after the activation.
        ([_group(3, "1.0", NOW - timedelta(days=5), LONG_AGO)], "retired"),
        ([_group(28, "1.0", LONG_AGO, PAST)], "retired"),
        ([_group(1, "1.0", None, PAST)], "retired"),
        ([_group(1, "1.0", PAST), _group(2, "2.0", PAST)], "FAIL: more than one active version"),
        ([_group(1, "1", PAST), _group(2, "1.0", PAST)], "FAIL: more than one active version"),
        ([_group(1, "beta", PAST)], "FAIL: active version is not dotted integers"),
        ([_group(1, None, PAST)], "FAIL: active version is not dotted integers"),
        # A fork or import that nobody activated, even beside a retired version.
        ([_group(1, "1.0", LONG_AGO, PAST), _group(2, "2.0")], "FAIL: no active version, never activated"),
        ([_group(1, "2.0", FUTURE)], "FAIL: no active version, scheduled"),
        # Activation is "not after now", the endpoint's own boundary.
        ([_group(1, "1.0", NOW)], "ok"),
        ([_group(1, "1.0", PAST, NOW)], "retired"),
    ],
)
def test_classify(groups, status):
    assert check.classify(groups, NOW) == status


def test_check_schema_groups_rows_by_pair():
    rows = [
        {"SourceDataModelId": 26, "TargetDataModelId": 17, **_group(26, "1.0", None, PAST)},
        {"SourceDataModelId": 26, "TargetDataModelId": 17, **_group(54, "3.0", PAST)},
        {"SourceDataModelId": 4, "TargetDataModelId": 1, **_group(3, "1.0", LONG_AGO, PAST)},
    ]
    assert check.check_schema("tenant_x", rows, NOW) == [
        {"schema": "tenant_x", "source": 26, "target": 17, "status": "ok", "groups": "26 v1.0, 54 v3.0"},
        {"schema": "tenant_x", "source": 4, "target": 1, "status": "retired", "groups": "3 v1.0"},
    ]


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


@pytest.fixture(scope="module")
def postgres_url():
    try:
        postgresql = testing.postgresql.Postgresql()
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    with postgresql:
        yield postgresql.url()


async def test_check_reads_public_then_tenants_and_skips_deleted_groups(postgres_url):
    conn = await asyncpg.connect(postgres_url)
    try:
        for schema in ("public", "tenant_b", "tenant_a", "other"):
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            await conn.execute(_TABLE.format(schema=schema))
            await conn.execute(
                f'INSERT INTO {schema}."TransformationsGroup" VALUES '
                "(1, 1, 2, '1.0', now() - interval '1 day', NULL, false), "
                # Deleted, so it is not a second active version.
                "(2, 1, 2, '2.0', now() - interval '1 day', NULL, true)"
            )
        await conn.execute("INSERT INTO tenant_a.\"TransformationsGroup\" VALUES (3, 5, 6, '1.0', NULL, NULL, false)")

        _, results = await check.check(conn)
    finally:
        await conn.close()

    assert list(results) == ["public", "tenant_a", "tenant_b"]
    assert [(p["source"], p["target"], p["status"]) for p in results["public"]] == [(1, 2, "ok")]
    assert [(p["source"], p["target"], p["status"]) for p in results["tenant_a"]] == [
        (1, 2, "ok"),
        (5, 6, "FAIL: no active version, never activated"),
    ]
