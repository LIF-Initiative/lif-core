#!/usr/bin/env python3
"""One-time backfill of TransformationsGroup.ActivationDate for #1350, through asyncpg.

The same backfill as `backfill-transformation-group-activation.sh`, for hosts that have
asyncpg but no psql, such as the `mdr-api` container reached through ECS exec. It runs
the script's SQL unchanged (a test keeps the two byte-for-byte equal) and only replaces
psql's variable interpolation: `:"schema"` becomes the quoted schema name and `:'schema'`
the same name as a literal. See the shell script's --help for the rules.

One transaction: `now()` (printed first as run_timestamp, which is what an undo matches
on), then the statement once per schema, `public` first and then every `tenant_*` schema
with a TransformationsGroup table, then ROLLBACK unless --apply.

Usage:
    POSTGRESQL_HOST=... POSTGRESQL_USER=... POSTGRESQL_PASSWORD=... POSTGRESQL_DB=... \\
        python3 backfill_transformation_group_activation.py [--apply]

POSTGRESQL_PORT defaults to 5432. These are the names the MDR API's own env uses.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg

SCHEMAS_SQL = r"""
SELECT table_schema FROM information_schema.tables
WHERE table_name = 'TransformationsGroup'
  AND (table_schema = 'public' OR table_schema LIKE 'tenant\_%')
ORDER BY table_schema <> 'public', table_schema
"""

# Must equal the heredoc in backfill-transformation-group-activation.sh.
BACKFILL_SQL = r"""WITH live_dated AS (
    -- The highest numeric version per pair that is already active.
    SELECT "SourceDataModelId", "TargetDataModelId",
           max(string_to_array(regexp_replace("GroupVersion", '(\.0+)+$', ''), '.')::numeric[]) AS active_key
    FROM :"schema"."TransformationsGroup"
    WHERE "Deleted" IS NOT TRUE
      AND "ActivationDate" <= now()
      AND ("DeprecationDate" IS NULL OR "DeprecationDate" > now())
      AND "GroupVersion" ~ '^[0-9]+(\.[0-9]+)*$'
    GROUP BY "SourceDataModelId", "TargetDataModelId"
), candidates AS (
    SELECT g."Id", g."SourceDataModelId", g."TargetDataModelId", g."GroupVersion",
           string_to_array(regexp_replace(g."GroupVersion", '(\.0+)+$', ''), '.')::numeric[] AS version_key,
           d.active_key
    FROM :"schema"."TransformationsGroup" AS g
    LEFT JOIN live_dated AS d USING ("SourceDataModelId", "TargetDataModelId")
    WHERE g."Deleted" IS NOT TRUE
      AND g."ActivationDate" IS NULL
      AND (g."DeprecationDate" IS NULL OR g."DeprecationDate" > now())
      AND g."GroupVersion" ~ '^[0-9]+(\.[0-9]+)*$'
), ranked AS (
    -- Only versions above the active one can be activated. top_key is NULL when there are none,
    -- and then every candidate in the pair is deprecated.
    SELECT *, max(version_key) FILTER (WHERE active_key IS NULL OR version_key > active_key) OVER pair AS top_key
    FROM candidates
    WINDOW pair AS (PARTITION BY "SourceDataModelId", "TargetDataModelId")
), counted AS (
    SELECT *, count(*) FILTER (WHERE version_key = top_key)
                  OVER (PARTITION BY "SourceDataModelId", "TargetDataModelId") AS top_count
    FROM ranked
), dated_below AS (
    -- Active dated versions below the version the pair keeps (the newly activated one, else its
    -- highest active one) are deprecated, as /activate does, so the pair ends with one active row.
    -- Pairs whose undated top is tied are skipped whole.
    SELECT g."Id"
    FROM :"schema"."TransformationsGroup" AS g
    JOIN live_dated AS d USING ("SourceDataModelId", "TargetDataModelId")
    LEFT JOIN (SELECT DISTINCT "SourceDataModelId", "TargetDataModelId", top_key, top_count FROM counted) AS p
        USING ("SourceDataModelId", "TargetDataModelId")
    WHERE g."Deleted" IS NOT TRUE
      AND g."ActivationDate" <= now()
      AND (g."DeprecationDate" IS NULL OR g."DeprecationDate" > now())
      AND g."GroupVersion" ~ '^[0-9]+(\.[0-9]+)*$'
      AND coalesce(p.top_count, 0) <= 1
      AND string_to_array(regexp_replace(g."GroupVersion", '(\.0+)+$', ''), '.')::numeric[]
          < coalesce(p.top_key, d.active_key)
), changes AS (
    SELECT "Id", version_key = top_key AS activate,
           CASE
               WHEN version_key = top_key THEN 'activated'
               WHEN version_key <= active_key THEN 'deprecated: at or below the active version'
               ELSE 'deprecated'
           END AS action
    FROM counted WHERE top_count <= 1
    UNION ALL
    SELECT "Id", false, 'deprecated: was active, below the version the pair keeps'
    FROM dated_below
), skipped AS (
    SELECT "Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion",
           'skipped: highest version is tied' AS action
    FROM counted WHERE top_count > 1
    UNION ALL
    SELECT "Id", "SourceDataModelId", "TargetDataModelId", "GroupVersion",
           'skipped: GroupVersion is not dotted integers'
    FROM :"schema"."TransformationsGroup"
    WHERE "Deleted" IS NOT TRUE
      AND "ActivationDate" IS NULL
      AND ("DeprecationDate" IS NULL OR "DeprecationDate" > now())
      AND ("GroupVersion" IS NULL OR "GroupVersion" !~ '^[0-9]+(\.[0-9]+)*$')
), updated AS (
    UPDATE :"schema"."TransformationsGroup" AS g
    SET "ActivationDate"  = CASE WHEN c.activate THEN now() ELSE g."ActivationDate" END,
        "DeprecationDate" = CASE WHEN c.activate THEN g."DeprecationDate" ELSE now() END
    FROM changes AS c
    WHERE g."Id" = c."Id"
    RETURNING g."Id", g."SourceDataModelId", g."TargetDataModelId", g."GroupVersion",
              CASE
                  WHEN c.activate AND g."DeprecationDate" IS NOT NULL
                      THEN 'activated: keeps its future DeprecationDate ' || g."DeprecationDate"
                  ELSE c.action
              END AS action
)
SELECT :'schema' AS schema, "SourceDataModelId" AS source, "TargetDataModelId" AS target,
       "Id" AS group_id, "GroupVersion" AS version, action
FROM (SELECT * FROM updated UNION ALL SELECT * FROM skipped) AS changes
ORDER BY source, target, action, group_id;"""

COLUMNS = ("schema", "source", "target", "group_id", "version", "action")


def render(schema: str) -> str:
    """BACKFILL_SQL for one schema, interpolated the way psql does it."""
    identifier = '"' + schema.replace('"', '""') + '"'
    literal = "'" + schema.replace("'", "''") + "'"
    return BACKFILL_SQL.replace(':"schema"', identifier).replace(":'schema'", literal)


async def backfill(conn: asyncpg.Connection, apply: bool) -> tuple[object, dict[str, list[asyncpg.Record]]]:
    """Run the backfill in every schema in one transaction; return run_timestamp and each schema's rows."""
    transaction = conn.transaction()
    await transaction.start()
    try:
        run_timestamp = await conn.fetchval("SELECT now()")
        schemas = [row["table_schema"] for row in await conn.fetch(SCHEMAS_SQL)]
        if not schemas:
            raise RuntimeError("No schema has a TransformationsGroup table")
        results = {schema: await conn.fetch(render(schema)) for schema in schemas}
    except BaseException:
        await transaction.rollback()
        raise
    if apply:
        await transaction.commit()
    else:
        await transaction.rollback()
    return run_timestamp, results


def format_rows(rows: list[asyncpg.Record]) -> str:
    """An aligned table with a row count, like psql's default output."""
    cells = [COLUMNS] + [tuple("" if row[c] is None else str(row[c]) for c in COLUMNS) for row in rows]
    widths = [max(len(line[i]) for line in cells) for i in range(len(COLUMNS))]
    lines = [" | ".join(value.ljust(width) for value, width in zip(line, widths)).rstrip() for line in cells]
    lines.insert(1, "-+-".join("-" * width for width in widths))
    lines.append(f"({len(rows)} row{'' if len(rows) == 1 else 's'})")
    return "\n".join(lines)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="commit (default: run, print, roll back)")
    args = parser.parse_args(argv)

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
        print(
            "DRY RUN: the updates run and are rolled back (use --apply to commit)"
            if not args.apply
            else f"Applying changes to {os.environ['POSTGRESQL_DB']} on {os.environ['POSTGRESQL_HOST']}"
        )
        run_timestamp, results = await backfill(conn, args.apply)
    finally:
        await conn.close()

    print(f"run_timestamp: {run_timestamp}")
    for schema, rows in results.items():
        print(f"=== {schema}")
        print(format_rows(rows))
    print("Committed" if args.apply else "Rolled back. Run with --apply to commit")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
