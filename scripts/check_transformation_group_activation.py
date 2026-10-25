#!/usr/bin/env python3
"""Read-only check that every transformation group pair has exactly one active version (#1350).

The gate before the Translator switches to the active-mapping endpoint
(`get_active_transformations_for_data_models`). That endpoint serves one active version per
(source, target) pair, so a pair that fails here returns a 404 or a 409 once the switch is live.

"Active" means what the endpoint means: not deleted, an ActivationDate that is not after now,
and a DeprecationDate that is null or after now. Each pair with a non-deleted group gets one status:

    ok                                         exactly one active version
    retired                                    no active version and nothing waiting to become
                                               active: every version is deprecated (expected;
                                               the endpoint returns 404 for it)
    FAIL: more than one active version         the endpoint serves the highest, or 409s on a tie
    FAIL: active version is not dotted integers  the endpoint ignores it, so the pair returns 404
    FAIL: no active version, never activated   a version has no ActivationDate (not activated)
    FAIL: no active version, scheduled         a version's ActivationDate is in the future

Reads `public` and every `tenant_*` schema with a TransformationsGroup table in one read-only
transaction, prints the pairs that are not ok and a count per schema, and exits 1 if any pair fails.

Usage:
    POSTGRESQL_HOST=... POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DB=... \\
        python3 check_transformation_group_activation.py

POSTGRESQL_PORT defaults to 5432. These are the names the MDR API's own env uses.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections import Counter
from datetime import datetime

import asyncpg

SCHEMAS_SQL = r"""
SELECT table_schema FROM information_schema.tables
WHERE table_name = 'TransformationsGroup'
  AND (table_schema = 'public' OR table_schema LIKE 'tenant\_%')
ORDER BY table_schema <> 'public', table_schema
"""

GROUPS_SQL = """
SELECT "Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion", "ActivationDate", "DeprecationDate"
FROM {schema}."TransformationsGroup"
WHERE "Deleted" IS NOT TRUE
ORDER BY "SourceDataModelId", "TargetDataModelId", "Id"
"""

# The same rule as GROUP_VERSION_PATTERN in lif.mdr_dto.transformation_group_dto.
GROUP_VERSION_PATTERN = re.compile(r"[0-9]+(\.[0-9]+)*")

COLUMNS = ("schema", "source", "target", "status", "groups")


def _live(deprecation: datetime | None, now: datetime) -> bool:
    return deprecation is None or deprecation > now


def classify(groups: list, now: datetime) -> str:
    """The status of one pair, from its non-deleted groups (see the module docstring)."""
    active = [
        g
        for g in groups
        if g["ActivationDate"] is not None and g["ActivationDate"] <= now and _live(g["DeprecationDate"], now)
    ]
    if len(active) > 1:
        return "FAIL: more than one active version"
    if active:
        if active[0]["GroupVersion"] and GROUP_VERSION_PATTERN.fullmatch(active[0]["GroupVersion"]):
            return "ok"
        return "FAIL: active version is not dotted integers"
    waiting = [g for g in groups if _live(g["DeprecationDate"], now)]
    if any(g["ActivationDate"] is None for g in waiting):
        return "FAIL: no active version, never activated"
    if waiting:
        return "FAIL: no active version, scheduled"
    return "retired"


def check_schema(schema: str, rows: list, now: datetime) -> list[dict]:
    """One result per pair in one schema."""
    pairs: dict[tuple[int, int], list] = {}
    for row in rows:
        pairs.setdefault((row["SourceDataModelId"], row["TargetDataModelId"]), []).append(row)
    return [
        {
            "schema": schema,
            "source": source,
            "target": target,
            "status": classify(groups, now),
            "groups": ", ".join(f"{g['Id']} v{g['GroupVersion']}" for g in groups),
        }
        for (source, target), groups in pairs.items()
    ]


async def check(conn: asyncpg.Connection) -> tuple[datetime, dict[str, list[dict]]]:
    """Every schema's pair results, read in one read-only snapshot."""
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        now = await conn.fetchval("SELECT now()")
        schemas = [row["table_schema"] for row in await conn.fetch(SCHEMAS_SQL)]
        if not schemas:
            raise RuntimeError("No schema has a TransformationsGroup table")
        results = {}
        for schema in schemas:
            identifier = '"' + schema.replace('"', '""') + '"'
            results[schema] = check_schema(schema, await conn.fetch(GROUPS_SQL.format(schema=identifier)), now)
    return now, results


def format_rows(rows: list[dict]) -> str:
    """An aligned table with a row count, like psql's default output."""
    cells = [COLUMNS] + [tuple(str(row[c]) for c in COLUMNS) for row in rows]
    widths = [max(len(line[i]) for line in cells) for i in range(len(COLUMNS))]
    lines = [" | ".join(value.ljust(width) for value, width in zip(line, widths)).rstrip() for line in cells]
    lines.insert(1, "-+-".join("-" * width for width in widths))
    lines.append(f"({len(rows)} row{'' if len(rows) == 1 else 's'})")
    return "\n".join(lines)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    missing = [name for name in ("POSTGRESQL_HOST", "POSTGRESQL_USER", "POSTGRESQL_DB") if not os.getenv(name)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(
        host=os.environ["POSTGRESQL_HOST"],
        port=int(os.getenv("POSTGRESQL_PORT") or 5432),
        user=os.environ["POSTGRESQL_USER"],
        password=os.getenv("POSTGRESQL_PASSWORD"),
        database=os.environ["POSTGRESQL_DB"],
    )
    try:
        now, results = await check(conn)
    finally:
        await conn.close()

    print(f"checked_at: {now}")
    failing = 0
    for schema, pairs in results.items():
        counts = Counter("FAIL" if p["status"].startswith("FAIL") else p["status"] for p in pairs)
        failing += counts["FAIL"]
        print(
            f"=== {schema}: {len(pairs)} pairs, {counts['ok']} ok, {counts['retired']} retired, {counts['FAIL']} failing"
        )
        not_ok = [p for p in pairs if p["status"] != "ok"]
        if not_ok:
            print(format_rows(not_ok))
    print(f"FAIL: {failing} pair{'' if failing == 1 else 's'} would not serve one version" if failing else "PASS")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
