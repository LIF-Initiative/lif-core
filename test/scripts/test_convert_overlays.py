"""Tests for the runner of #1388's overlay conversion.

The runner writes to every schema of a live MDR, so these pin what it must not do: start before #1479's
cleanup, touch a schema that's already converted, or leave anything behind on a dry run; and that a
dry run still writes its undo record and --apply commits. Each test gets a fresh copy of backup.sql. They need a local PostgreSQL (`initdb`
and `psql`) and skip without one.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
from itertools import count
from urllib.parse import urlparse

import asyncpg
import pytest
import testing.postgresql
from sqlalchemy.ext.asyncio import create_async_engine

_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load("convert_overlays")
_COPIES = count()
_TABLES = ("Entities", "Attributes", "EntityAssociation", "EntityAttributeAssociation", "ExtInclusionsFromBaseDM",
           "ValueSets", "ValueSetValues", "TransformationAttributes", "DataModels")  # fmt: skip


@pytest.fixture(scope="module")
def seed_server():
    """A local PostgreSQL with backup.sql loaded into a template database named seed."""
    try:
        postgresql = testing.postgresql.Postgresql()
    except RuntimeError as e:
        pytest.skip(f"PostgreSQL not available locally: {e}")
    with postgresql:
        url = urlparse(postgresql.url())
        env = {**os.environ, "PGPASSWORD": url.password or ""}
        base = ["-h", url.hostname, "-p", str(url.port), "-U", url.username]
        subprocess.run(["psql", *base, "-d", url.path.lstrip("/"), "-c", "CREATE DATABASE seed"], env=env, check=True)
        result = subprocess.run(
            ["psql", *base, "-d", "seed", "-f", str(_ROOT / "projects/lif_mdr_database/backup.sql")],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.fail(f"Failed to load backup.sql: {result.stderr}")
        yield url


@pytest.fixture
async def seed_copy(seed_server):
    """(asyncpg connection, SQLAlchemy engine) on a fresh copy of the seed."""
    name = f"seed_copy_{next(_COPIES)}"
    password = f":{seed_server.password}" if seed_server.password else ""
    root = f"{seed_server.username}{password}@{seed_server.hostname}:{seed_server.port}"
    admin = await asyncpg.connect(f"postgresql://{root}/postgres")
    try:
        await admin.execute(f"CREATE DATABASE {name} TEMPLATE seed")
    finally:
        await admin.close()
    conn = await asyncpg.connect(f"postgresql://{root}/{name}")
    engine = create_async_engine(f"postgresql+asyncpg://{root}/{name}")
    try:
        yield conn, engine
    finally:
        await engine.dispose()
        await conn.close()


async def _cleaned(conn):
    await _load("cleanup_export_blockers").cleanup(conn, apply=True)
    await _load("remove_test_data").cleanup(conn, apply=True)


async def _snapshot(conn):
    """Every row of the tables the conversion writes, as text, so any change shows."""
    return {table: await conn.fetch(f'SELECT t::text FROM "{table}" t ORDER BY "Id"') for table in _TABLES}


async def test_it_refuses_to_start_before_the_test_data_is_removed(seed_copy, tmp_path):
    conn, engine = seed_copy
    before = await _snapshot(conn)

    ok, lines = await runner.convert_schema(engine, "public", apply=True, undo_dir=tmp_path)

    assert not ok
    assert "run remove_test_data.py first" in lines[0] and "model 25" in lines[0]
    assert await _snapshot(conn) == before
    assert not list(tmp_path.iterdir())


async def test_a_converted_schema_is_skipped(seed_copy, tmp_path):
    conn, engine = seed_copy
    await _cleaned(conn)
    await conn.execute('UPDATE "DataModels" SET "BaseDataModelId" = NULL WHERE "Id" IN (17, 18)')
    await conn.execute('UPDATE "ExtInclusionsFromBaseDM" SET "Deleted" = true WHERE "ExtDataModelId" IN (17, 18)')
    before = await _snapshot(conn)

    ok, lines = await runner.convert_schema(engine, "public", apply=True, undo_dir=tmp_path)

    assert (ok, lines) == (True, ["  already converted, skipped"])
    assert await _snapshot(conn) == before


def _undo(tmp_path):
    return json.loads((tmp_path / "public.json").read_text())


async def _overlays_left(conn):
    return await conn.fetchval(
        'SELECT count(*) FROM "ExtInclusionsFromBaseDM" WHERE "Deleted" = false AND "ExtDataModelId" IN (17, 18)'
    )


async def test_a_dry_run_converts_writes_the_undo_record_and_leaves_the_schema_as_it_was(seed_copy, tmp_path):
    conn, engine = seed_copy
    await _cleaned(conn)
    before = await _snapshot(conn)

    ok, _ = await runner.convert_schema(engine, "public", apply=False, undo_dir=tmp_path)

    assert ok
    assert await _snapshot(conn) == before
    undo = _undo(tmp_path)
    assert (undo["schema"], undo["committed"]) == ("public", False)
    assert sorted(undo["id_maps"]) == ["17", "18"]


async def test_apply_commits_and_a_re_run_skips(seed_copy, tmp_path):
    conn, engine = seed_copy
    await _cleaned(conn)
    assert await _overlays_left(conn) > 0

    ok, _ = await runner.convert_schema(engine, "public", apply=True, undo_dir=tmp_path)

    assert ok
    assert _undo(tmp_path)["committed"] is True
    assert await _overlays_left(conn) == 0
    bases = await conn.fetch('SELECT "BaseDataModelId" FROM "DataModels" WHERE "Id" IN (17, 18)')
    assert [row[0] for row in bases] == [None, None]
    after = await _snapshot(conn)

    assert await runner.convert_schema(engine, "public", apply=True, undo_dir=tmp_path) == (
        True,
        ["  already converted, skipped"],
    )
    assert await _snapshot(conn) == after
