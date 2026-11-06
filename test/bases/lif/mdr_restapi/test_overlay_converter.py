"""The overlay conversion on the seed (#1388).

The seed still holds the test data #1444 and #1479 remove before the conversion runs, so each test runs
both cleanups first, then converts models 17 and 18 in one transaction, as the runner does. The
conversion checks itself (every touched model, all 16 flag combinations, against the rewritten
baseline); these tests pin what it did.
"""

import importlib.util
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from lif.mdr_services.overlay_converter import ConversionFailed, convert_overlays

_ROOT = pathlib.Path(__file__).resolve().parents[4]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
async def cleaned_seed(seed_postgres):
    """The seed after #1444's and #1479's cleanups, as the conversion finds dev."""
    conn = await asyncpg.connect(seed_postgres.url())
    try:
        await _load("cleanup_export_blockers").cleanup(conn, apply=True)
        await _load("remove_test_data").cleanup(conn, apply=True)
    finally:
        await conn.close()
    return seed_postgres


@pytest.fixture
async def session(cleaned_seed):
    url = urlparse(cleaned_seed.url())
    engine = create_async_engine(
        f"postgresql+asyncpg://{url.username}:{url.password or ''}@{url.hostname}:{url.port}{url.path}"
    )
    maker = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def test_the_seed_converts_and_passes_every_check(session):
    try:
        report = await convert_overlays(session, [17, 18])
    except ConversionFailed as e:
        pytest.fail("\n\n".join(e.reasons))

    assert report.compared, report
    print({m.model_id: m.copied for m in report.models})
    print({m.model_id: {k: len(v) for k, v in m.soft_deleted.items()} for m in report.models})
    print(report.moved_attributes, {m.model_id: m.updated_mapping_rows for m in report.models})
    left = await session.execute(
        text('SELECT count(*) FROM "ExtInclusionsFromBaseDM" WHERE "Deleted" = false AND "ExtDataModelId" IN (17, 18)')
    )
    assert left.scalar() == 0
