"""Tests for the #1393 read-only count of what keeps each model, mapping group and crosswalk from exporting.

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

from lif.mdr_portability import PortabilityError, PortabilityErrorCode
from lif.mdr_portability.errors import error_group

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
        # CI must prove the database tests ran; skipping there would pass them unproven (#1063).
        if os.environ.get("CI"):
            pytest.fail(f"PostgreSQL not available in CI: {e}")
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
    # #1513 ran #1444's cleanup, removed the test data and model 16, and converted 17 and 18. What's left
    # in public is models 3 (CLR v2), 6 (Ed-Fi v5), 14 (CASE) and 29 (Open Badges v3), whose seed content
    # still has attributes with DataType entity; #1513's next step replaces it.
    assert public.overlays == []
    assert (public.models, public.models_exported, public.models_refused) == (19, 15, 4)
    assert (public.groups, public.groups_exported, public.groups_refused) == (6, 6, 0)
    # Every crosswalk in the seed exports, so none adds a refusal below (#1513). #1520 removed the test
    # data, which took the 343 -> 347 crosswalk with it.
    assert (public.crosswalks, public.crosswalks_exported, public.crosswalks_refused) == (6, 6, 0)
    assert _counts(public) == {
        "NOT_MIGRATED: the attribute has DataType entity; it becomes an association to the entity": 190
    }
    labels = {
        label
        for label, _ in public.refusals[
            "NOT_MIGRATED: the attribute has DataType entity; it becomes an association to the entity"
        ]
    }
    assert labels == {"model 3 CLR v2", "model 6 Ed-Fi v5", "model 14 CASE", "model 29 Open Badges v3"}

    tenant = results["tenant_lif_team"]
    assert (tenant.models, tenant.models_exported, tenant.models_refused, tenant.overlays) == (18, 18, 0, [])
    assert (tenant.groups, tenant.groups_exported, tenant.groups_refused) == (6, 6, 0)


async def test_measure_writes_nothing_and_counts_a_failed_export(seed_url, monkeypatch):
    export_model = measure.export_model

    async def failing_export_model(session, data_model_id):
        if data_model_id == 1:
            raise RuntimeError("converter bug")
        if data_model_id == 3:
            # No message: the error is still recorded, and the run goes on.
            raise AssertionError()
        if data_model_id == 2:
            # The transaction is read-only, so this fails, and the savepoint keeps the run going.
            await session.execute(text('UPDATE "DataModels" SET "Notes" = \'changed\' WHERE "Id" = 2'))
        return await export_model(session, data_model_id)

    monkeypatch.setattr(measure, "export_model", failing_export_model)
    results = await _measure(seed_url)

    public = results["public"]
    assert public.refusals["ERROR: RuntimeError"] == [("model 1 LIF", "converter bug")]
    [(label, message)] = public.refusals["ERROR: AssertionError"]
    assert label.startswith("model 3 ") and message == ""
    [(label, message)] = public.refusals["ERROR: DBAPIError"]
    assert label == "model 2 HR Open"
    assert "read-only transaction" in message
    # The rest of the schema, and the next schema, were still measured.
    assert (public.groups, public.groups_exported) == (6, 6)
    # In tenant_lif_team every model exports, except the three this test breaks.
    assert results["tenant_lif_team"].models_exported == 15

    engine = create_async_engine(seed_url)
    try:
        async with engine.connect() as conn:
            notes = await conn.scalar(text('SELECT "Notes" FROM "DataModels" WHERE "Id" = 2'))
    finally:
        await engine.dispose()
    assert notes != "changed"


async def test_measure_counts_a_refused_crosswalk_under_its_reason(seed_url, monkeypatch):
    export_crosswalk = measure.export_crosswalk

    async def refusing_export_crosswalk(session, source_value_set_id, target_value_set_id):
        if (source_value_set_id, target_value_set_id) == (315, 290):
            raise error_group(
                [
                    PortabilityError(
                        PortabilityErrorCode.CROSSWALK_SOURCE_DUPLICATE, "Entries[3].Source", "'Grade 9' maps twice"
                    )
                ]
            )
        return await export_crosswalk(session, source_value_set_id, target_value_set_id)

    monkeypatch.setattr(measure, "export_crosswalk", refusing_export_crosswalk)
    public = (await _measure(seed_url))["public"]

    assert (public.crosswalks, public.crosswalks_exported, public.crosswalks_refused) == (6, 5, 1)
    assert public.refusals["CROSSWALK_SOURCE_DUPLICATE: … maps twice"] == [
        ("crosswalk 315 -> 290", "Entries[3].Source")
    ]
    assert "crosswalks 5 export, 1 refused" in measure.format_result(public, False)[0]
