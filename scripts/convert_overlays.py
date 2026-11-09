#!/usr/bin/env python3
"""Convert the overlay models 17 and 18 into self-contained models, in place (#1388, ADR data_model/0004).

Runs `lif.mdr_services.overlay_converter.convert_overlays` in `public` and then every `tenant_*` schema
with a DataModels table, each in its own transaction with the schema on `search_path`, as the MDR API's
tenant sessions do. The conversion checks itself before anything commits: every model it touches must
generate the same schema in all 16 flag combinations (after its Id map), and 17, 18 and their mapping
groups must export. A schema whose check fails is rolled back and reported; the other schemas still run.

Before converting a schema it refuses to start while #1479's test data is still there (model 25, or any
of `remove_test_data.py`'s pinned rows, live): the conversion's baseline must be taken after that
cleanup. A schema where 17 and 18 are already converted (no inclusion rows, no BaseDataModelId) is
skipped, so a re-run converts only what's left.

Each schema's undo record (the Id map, every row inserted or soft-deleted, and the old value of every
column updated in place) is written to `<undo-dir>/<schema>.json`, on a dry run too. Copy the directory
out of the container before it stops.

Each schema's transaction first locks every table the conversion reads or writes (EXCLUSIVE: reads go
on, writes wait until it commits or rolls back), so an MDR edit can't commit mid-run and be lost. A
schema that can't get the locks within LOCK_TIMEOUT is skipped and reported. Pause MDR edits anyway.

ROLLBACK unless --apply. Exits 1 if any schema refused, failed its checks or couldn't lock.

Usage, in an image with the MDR API's packages (the mdr-api container has them):
    POSTGRESQL_HOST=... POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DB=... \\
        python3 convert_overlays.py [--apply] [--undo-dir DIR]

POSTGRESQL_PORT defaults to 5432. These are the names the MDR API's own env uses.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import importlib.util
import json
import os
import pathlib
import sys

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lif.mdr_services.overlay_converter import ConversionFailed, Report, convert_overlays

OVERLAYS = [17, 18]

# Every table the conversion reads or writes. Locked for the whole transaction so no edit commits
# between the conversion reading a row and committing (an inclusion row added mid-run would be deleted
# without its element copied). Reads go on; writes wait. A schema that can't get the locks in time is
# rolled back and reported.
LOCKED_TABLES = ("DataModels", "Entities", "Attributes", "EntityAssociation", "EntityAttributeAssociation",
                 "ExtInclusionsFromBaseDM", "ValueSets", "ValueSetValues", "TransformationsGroup", "Transformations",
                 "TransformationAttributes")  # fmt: skip
LOCK_TIMEOUT = "10s"
LOCK_NOT_AVAILABLE = "55P03"

SCHEMAS_SQL = r"""
SELECT table_schema FROM information_schema.tables
WHERE table_name = 'DataModels'
  AND (table_schema = 'public' OR table_schema LIKE 'tenant\_%')
ORDER BY table_schema <> 'public', table_schema
"""


def _load_test_data_pins():
    spec = importlib.util.spec_from_file_location(
        "remove_test_data", pathlib.Path(__file__).with_name("remove_test_data.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _test_data_left(session: AsyncSession) -> list[str]:
    """What's still live of #1479's test data: model 25 and its pinned entities and attributes."""
    pins = _load_test_data_pins()
    left = []
    model_id, model_name = pins.TEST_MODEL
    if (
        await session.execute(
            text('SELECT 1 FROM "DataModels" WHERE "Id" = :i AND "Name" = :n AND "Deleted" = false'),
            {"i": model_id, "n": model_name},
        )
    ).first():
        left.append(f"model {model_id}")
    for table, rows in (
        ("Entities", pins.SEED_ENTITIES + pins.DEV_ENTITIES),
        ("Attributes", pins.SEED_ATTRIBUTES + pins.DEV_ATTRIBUTES),
    ):
        for row_id, data_model_id, unique_name in rows:
            if (
                await session.execute(
                    text(
                        f'SELECT 1 FROM "{table}" WHERE "Id" = :i AND "DataModelId" = :m AND "UniqueName" = :u '
                        'AND "Deleted" = false'
                    ),
                    {"i": row_id, "m": data_model_id, "u": unique_name},
                )
            ).first():
                left.append(f"{table} {row_id}")
    return left


async def _overlays_left(session: AsyncSession) -> list[int]:
    """Which of 17 and 18 are still overlays here, in order."""
    rows = await session.execute(
        text(
            'SELECT m."Id" FROM "DataModels" m WHERE m."Id" = ANY(:ids) AND m."Deleted" = false '
            'AND (m."BaseDataModelId" IS NOT NULL OR EXISTS (SELECT 1 FROM "ExtInclusionsFromBaseDM" i '
            'WHERE i."ExtDataModelId" = m."Id" AND i."Deleted" = false)) ORDER BY m."Id"'
        ),
        {"ids": OVERLAYS},
    )
    return [row[0] for row in rows]


def undo_record(schema: str, report: Report, committed: bool) -> dict:
    return {
        "schema": schema,
        "committed": committed,
        "moved_attributes": report.moved_attributes,
        "id_maps": {str(m.model_id): dataclasses.asdict(m.id_map) for m in report.models},
        "changes": dataclasses.asdict(report.changes),
    }


def write_undo_record(undo_dir: pathlib.Path, schema: str, report: Report, committed: bool) -> None:
    undo_dir.mkdir(parents=True, exist_ok=True)
    record = undo_record(schema, report, committed)
    (undo_dir / f"{schema}.json").write_text(json.dumps(record, indent=2, default=str))


def summary(report: Report) -> list[str]:
    lines = [f"  step 0 moved {len(report.moved_attributes)} attributes: {sorted(report.moved_attributes)}"]
    for model in report.models:
        copied = ", ".join(f"{kind} {n}" for kind, n in model.copied.items())
        deleted = ", ".join(f"{table} {len(ids)}" for table, ids in model.soft_deleted.items())
        lines.append(f"  model {model.model_id}: copied {copied}")
        lines.append(f"  model {model.model_id}: soft-deleted {deleted}")
        lines.append(f"  model {model.model_id}: mapping rows re-pointed {model.updated_mapping_rows}")
    lines.append(f"  checked models {sorted(report.compared)}, 16 combinations each")
    return lines


async def convert_schema(engine, schema: str, apply: bool, undo_dir: pathlib.Path) -> tuple[bool, list[str]]:
    """Convert one schema in its own transaction. Returns (ok, lines to print)."""
    identifier = '"' + schema.replace('"', '""') + '"'
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            # `public` stays on the path for its enum types, as in the API's tenant sessions.
            await session.execute(text(f"SET LOCAL search_path TO {identifier}, public"))
            await session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
            try:
                tables = ", ".join(f'"{table}"' for table in LOCKED_TABLES)
                await session.execute(text(f"LOCK TABLE {tables} IN EXCLUSIVE MODE"))
            except DBAPIError as e:
                if getattr(e.orig, "sqlstate", None) != LOCK_NOT_AVAILABLE:
                    raise
                return False, [f"  not started: another transaction is writing; no locks within {LOCK_TIMEOUT}"]
            overlays = await _overlays_left(session)
            if not overlays:
                return True, ["  already converted, skipped"]
            left = await _test_data_left(session)
            if left:
                return False, [f"  refused: run remove_test_data.py first; still live: {', '.join(left)}"]
            try:
                report = await convert_overlays(session, overlays)
            except ConversionFailed as e:
                return False, ["  failed, rolled back:", *(f"    - {reason}" for reason in e.reasons)]
            # Written before the commit and marked committed only once it has, so a failed commit
            # leaves a record that says so.
            write_undo_record(undo_dir, schema, report, committed=False)
            if apply:
                await session.commit()
        except Exception as e:  # noqa: BLE001 - one schema's error mustn't stop the others
            return False, [f"  failed, rolled back: {type(e).__name__}: {e}"]
        finally:
            # A no-op after a commit; otherwise every change in this schema is discarded.
            await session.rollback()
        if apply:
            write_undo_record(undo_dir, schema, report, committed=True)
        return True, summary(report)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="commit (default: run, check, roll back)")
    parser.add_argument("--undo-dir", default="overlay-conversion-undo", help="where each schema's undo record goes")
    args = parser.parse_args(argv)

    missing = [name for name in ("POSTGRESQL_HOST", "POSTGRESQL_USER", "POSTGRESQL_DB") if not os.getenv(name)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    engine = create_async_engine(
        URL.create(
            "postgresql+asyncpg",
            username=os.environ["POSTGRESQL_USER"],
            password=os.getenv("POSTGRESQL_PASSWORD"),
            host=os.environ["POSTGRESQL_HOST"],
            port=int(os.getenv("POSTGRESQL_PORT") or 5432),
            database=os.environ["POSTGRESQL_DB"],
        )
    )
    print("APPLY: each schema commits if its checks pass" if args.apply else "DRY RUN: every schema rolls back")
    failed = []
    try:
        async with engine.connect() as conn:
            schemas = [row[0] for row in await conn.execute(text(SCHEMAS_SQL))]
        for schema in schemas:
            ok, lines = await convert_schema(engine, schema, args.apply, pathlib.Path(args.undo_dir))
            print(f"=== {schema}: {'ok' if ok else 'NOT CONVERTED'}")
            print("\n".join(lines))
            if not ok:
                failed.append(schema)
    finally:
        await engine.dispose()
    print(f"Undo records in {args.undo_dir}/")
    if failed:
        print(f"Not converted: {', '.join(failed)}")
        return 1
    print("Committed" if args.apply else "Rolled back. Run with --apply to commit")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
