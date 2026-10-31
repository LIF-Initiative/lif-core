#!/usr/bin/env python3
"""Read-only count of what keeps each model and mapping group from exporting as a portable file (#1393).

Export refuses rows the portable format can't represent (Portability Spec §10, §11). Rather than
restate those rules in SQL, this runs the converters themselves, `export_model` on every live model
and `export_mapping_group` on every non-deleted transformation group, in every schema, and counts what
they refuse. A count is therefore exactly what an export would hit today, and it stays right when a
converter's rules change.

For each schema it prints how many models and groups export and how many are refused, then each
refusal reason with the number of elements it names and the models or groups it names them in.
Names inside a reason (a value set, a model) are folded into `…` so the same rule counts as one
reason. Overlay models are refused on that alone and are #1388's to convert; they are listed apart
and not counted as cleanup. An export that fails with anything other than a refusal is counted as an
`ERROR` reason, so one broken row can't hide the rest of the schema.

Reads `public` and every `tenant_*` schema with a DataModels table, each in a read-only transaction
with the schema on `search_path`, as the MDR API's tenant sessions do. It changes nothing and exits
0; it exits 1 only when it cannot connect or find a schema.

Usage, in an image with the MDR API's packages (the mdr-api container has them):
    POSTGRESQL_HOST=... POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DB=... \\
        python3 measure_export_blockers.py [--details]

POSTGRESQL_PORT defaults to 5432. These are the names the MDR API's own env uses. `--details` also
lists every refused element.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lif.mdr_portability import PortabilityErrorGroup
from lif.mdr_services.model_converter import is_overlay
from lif.mdr_services.portability_converter import export_mapping_group, export_model
from lif.mdr_sql_model.core import DataModel, TransformationGroup

SCHEMAS_SQL = r"""
SELECT table_schema FROM information_schema.tables
WHERE table_name = 'DataModels'
  AND (table_schema = 'public' OR table_schema LIKE 'tenant\_%')
ORDER BY table_schema <> 'public', table_schema
"""

# A quoted name inside a reason: 'Ed-Fi v5', "Exit Reason".
_QUOTED = re.compile(r"""'[^']*'|"[^"]*\"""")
# A bare number inside a reason: "model 17 is not installed", "has 3 constraint rows". Not one in a
# path such as "ADR data_model/0004".
_NUMBER = re.compile(r"(?<![\w/])\d+\b")


def reason_key(code: str, reason: str) -> str:
    """One refusal rule, with the names and numbers of a particular case folded away."""
    return f"{code}: {_NUMBER.sub('N', _QUOTED.sub('…', reason))}"


@dataclass
class SchemaResult:
    schema: str
    models: int = 0
    models_exported: int = 0
    overlays: list[str] = field(default_factory=list)
    groups: int = 0
    groups_exported: int = 0
    # reason key -> the refused elements, as (model or group label, element)
    refusals: dict[str, list[tuple[str, str]]] = field(default_factory=lambda: defaultdict(list))

    @property
    def models_refused(self) -> int:
        return self.models - self.models_exported - len(self.overlays)

    @property
    def groups_refused(self) -> int:
        return self.groups - self.groups_exported


def _model_label(model: DataModel) -> str:
    return f"model {model.Id} {model.Name}"


def _group_label(group: TransformationGroup) -> str:
    return f"group {group.Id} ({group.SourceDataModelId} -> {group.TargetDataModelId} v{group.GroupVersion})"


async def _try_export(session: AsyncSession, result: SchemaResult, label: str, export) -> bool:
    """Run one export in a savepoint; record its refusals, or its error, and say whether it exported."""
    try:
        async with session.begin_nested():
            await export()
        return True
    except PortabilityErrorGroup as group:
        for error in group.exceptions:
            result.refusals[reason_key(error.code.value, error.reason)].append((label, error.element))
    except Exception as error:  # noqa: BLE001 - a crash is a blocker too, and the run goes on
        result.refusals[f"ERROR: {type(error).__name__}"].append((label, str(error).splitlines()[0][:200]))
    return False


async def measure_schema(session: AsyncSession, schema: str) -> SchemaResult:
    """Export every live model and non-deleted group in the schema on the session's search_path."""
    result = SchemaResult(schema)
    models = (
        (await session.execute(select(DataModel).where(DataModel.Deleted.is_not(True)).order_by(DataModel.Id)))
        .scalars()
        .all()
    )
    for model in models:
        result.models += 1
        if await is_overlay(session, model):
            result.overlays.append(_model_label(model))
            continue
        if await _try_export(session, result, _model_label(model), lambda: export_model(session, model.Id)):
            result.models_exported += 1

    groups = (
        (
            await session.execute(
                select(TransformationGroup)
                .where(TransformationGroup.Deleted.is_not(True))
                .order_by(TransformationGroup.Id)
            )
        )
        .scalars()
        .all()
    )
    for transformation_group in groups:
        result.groups += 1
        label = _group_label(transformation_group)
        if await _try_export(session, result, label, lambda: export_mapping_group(session, transformation_group.Id)):
            result.groups_exported += 1
    return result


async def measure(engine) -> list[SchemaResult]:
    """Every schema's result, each schema read in its own read-only transaction."""
    async with engine.connect() as conn:
        schemas = [row[0] for row in await conn.execute(text(SCHEMAS_SQL))]
    if not schemas:
        raise RuntimeError("No schema has a DataModels table")
    results = []
    for schema in schemas:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION READ ONLY"))
                identifier = '"' + schema.replace('"', '""') + '"'
                # `public` stays on the path for its enum types, as in the API's tenant sessions.
                await session.execute(text(f"SET LOCAL search_path TO {identifier}, public"))
                results.append(await measure_schema(session, schema))
    return results


def format_result(result: SchemaResult, details: bool) -> list[str]:
    lines = [
        f"=== {result.schema}: models {result.models_exported} export, {result.models_refused} refused,"
        f" {len(result.overlays)} overlays; groups {result.groups_exported} export, {result.groups_refused} refused"
    ]
    if result.overlays:
        lines.append(f"  overlays (#1388): {', '.join(result.overlays)}")
    for key in sorted(result.refusals, key=lambda k: (-len(result.refusals[k]), k)):
        refused = result.refusals[key]
        labels = list(dict.fromkeys(label for label, _ in refused))
        lines.append(f"  {len(refused):>6}  {key}")
        lines.append(f"          in {', '.join(labels)}")
        if details:
            lines.extend(f"          - {label}: {element}" for label, element in refused)
    return lines


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--details", action="store_true", help="list every refused element")
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
    try:
        results = await measure(engine)
    finally:
        await engine.dispose()

    for result in results:
        print("\n".join(format_result(result, args.details)))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
