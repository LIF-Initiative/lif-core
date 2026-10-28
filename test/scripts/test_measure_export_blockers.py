"""Tests for the #1393 read-only count of what keeps each model and mapping group from exporting.

The counts decide which data gets cleaned up, in every schema, so a count that drifts from what
export actually refuses would send the cleanup after the wrong rows. The seed test pins the figures
for `public` in backup.sql; update them when the seed or a converter rule changes. It needs a local
PostgreSQL (`initdb` and `psql`) and skips without one, like the MDR tests.
"""

import importlib.util
import os
import pathlib
import subprocess
import sys
from urllib.parse import urlparse

import pytest
import testing.postgresql
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "measure_export_blockers", _ROOT / "scripts" / "measure_export_blockers.py"
)
measure = importlib.util.module_from_spec(_spec)
# Registered first: @dataclass resolves its annotations through sys.modules.
sys.modules[_spec.name] = measure
_spec.loader.exec_module(measure)


@pytest.mark.parametrize(
    "code, reason, key",
    [
        (
            "NOT_MIGRATED",
            "the value set 'Grade Levels' is in another model",
            "NOT_MIGRATED: the value set … is in another model",
        ),
        ("NOT_MIGRATED", "the model has 3 constraint rows", "NOT_MIGRATED: the model has N constraint rows"),
        # A number inside a path is part of the rule, not a case of it.
        (
            "NOT_MIGRATED",
            "'StateU LIF' is an overlay; convert it first (ADR data_model/0004)",
            "NOT_MIGRATED: … is an overlay; convert it first (ADR data_model/0004)",
        ),
    ],
)
def test_reason_key_folds_names_and_numbers(code, reason, key):
    assert measure.reason_key(code, reason) == key


@pytest.fixture(scope="module")
def seed_url():
    try:
        postgresql = testing.postgresql.Postgresql()
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    with postgresql:
        url = urlparse(postgresql.url())
        result = subprocess.run(
            [
                "psql",
                "-h",
                url.hostname,
                "-p",
                str(url.port),
                "-U",
                url.username,
                "-d",
                url.path.lstrip("/"),
                "-f",
                str(_ROOT / "projects/lif_mdr_database/backup.sql"),
            ],
            env={**os.environ, "PGPASSWORD": url.password or ""},
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Failed to load backup.sql: {result.stderr}")
        yield postgresql.url().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _measure(url):
    engine = create_async_engine(url)
    try:
        return {result.schema: result for result in await measure.measure(engine)}
    finally:
        await engine.dispose()


def _counts(result):
    return {key: len(refused) for key, refused in result.refusals.items()}


async def test_measure_reports_what_the_seed_refuses(seed_url):
    results = await _measure(seed_url)

    assert list(results) == ["public", "tenant_lif_team"]
    public = results["public"]
    assert public.overlays == ["model 17 StateU LIF", "model 18 Org2 LIF"]
    assert (public.models, public.models_exported, public.models_refused) == (21, 1, 18)
    assert (public.groups, public.groups_exported, public.groups_refused) == (9, 2, 7)
    assert _counts(public) == {
        "NOT_MIGRATED: the attribute has no DataType; migration sets string": 921,
        "NOT_MIGRATED: the attribute has DataType entity; it becomes an association to the entity": 190,
        "NOT_MIGRATED: the attribute is in no association; migration drops it": 77,
        "NOT_MIGRATED: the association is declared with ExtendedByDataModelId": 62,
        "NOT_MIGRATED: the child … is in another model": 8,
        "NOT_MIGRATED: … is an overlay; convert it first (ADR data_model/0004)": 6,
        "NOT_MIGRATED: model N declared it between two models it does not own, so it belongs to no model": 2,
        "MAPPING_TARGET_MISSING: the transformation has N targets": 1,
        "MODEL_IDENTITY_INCOMPLETE: Field required": 1,
        "MODEL_IDENTITY_INCOMPLETE: the model has no ContributorOrganization": 1,
        "NOT_MIGRATED: the value uses Extension": 1,
    }
    # Dereck's no-target transformation (1189), and the model with no organization.
    assert public.refusals["MAPPING_TARGET_MISSING: the transformation has N targets"][0][0] == "group 3 (4 -> 1 v1.0)"
    assert public.refusals["MODEL_IDENTITY_INCOMPLETE: Field required"][0][0] == "model 26 R1 Demo Source Data Model"


async def test_measure_writes_nothing_and_counts_a_failed_export(seed_url, monkeypatch):
    export_model = measure.export_model

    async def failing_export_model(session, data_model_id):
        if data_model_id == 1:
            raise RuntimeError("converter bug")
        if data_model_id == 2:
            # The transaction is read-only, so this fails, and the savepoint keeps the run going.
            await session.execute(text('UPDATE "DataModels" SET "Notes" = \'changed\' WHERE "Id" = 2'))
        return await export_model(session, data_model_id)

    monkeypatch.setattr(measure, "export_model", failing_export_model)
    results = await _measure(seed_url)

    public = results["public"]
    assert public.refusals["ERROR: RuntimeError"] == [("model 1 LIF", "converter bug")]
    [(label, message)] = public.refusals["ERROR: DBAPIError"]
    assert label == "model 2 HR Open"
    assert "read-only transaction" in message
    # The rest of the schema, and the next schema, were still measured.
    assert (public.groups, public.groups_exported) == (9, 2)
    assert results["tenant_lif_team"].models_exported == 1

    engine = create_async_engine(seed_url)
    try:
        async with engine.connect() as conn:
            notes = await conn.scalar(text('SELECT "Notes" FROM "DataModels" WHERE "Id" = 2'))
    finally:
        await engine.dispose()
    assert notes != "changed"
