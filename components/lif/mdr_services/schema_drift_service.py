"""Report what the database actually has, so migration drift stops being silent (#1226).

Two different drifts can hide a migration, and each is invisible to the check for
the other:

1. **The migration never ran.** Flyway only runs when a new image tag is deployed
   to the ``mdr-database`` SAM stack, which no service workflow does. A merged
   ``V*.sql`` therefore sits unapplied until someone runs the procedure by hand
   (#1123, and V1.6 for six weeks).
2. **The migration ran, but not where queries land.** Migrations are written
   ``ALTER TABLE public."…"`` while tenant schemas are point-in-time clones that
   never receive them. ``flyway_schema_history`` reports Success and the column is
   still missing from every schema the application serves (#1265).

The second is why reading ``flyway_schema_history`` alone is not enough: on
2026-09-17 it read version 1.6 on both environments while all 19 tenant schemas
lacked the column that migration added.

This module reports raw state only. Deciding whether that state is *wrong* needs
the repo's migration files, which the database has no business knowing about, so
the comparison lives in ``scripts/check-migration-drift.py``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Tenant schemas are named `tenant_{group}` (`lif.tenant_routing.SCHEMA_PREFIX`), and
# V1.5 already enumerates them this way. Matching the prefix is more precise than
# "everything that is not public" -- an extension or tooling schema would otherwise be
# counted as clean and inflate the denominator.
_TENANT_SCHEMA_PATTERN = "^tenant_"

# The schema Flyway records its history in -- its own default schema for this stack.
_HISTORY_SCHEMA = "public"


async def applied_migrations(session: AsyncSession) -> list[dict[str, Any]]:
    """Every versioned row of ``flyway_schema_history``, newest first.

    Returns an empty list when the table does not exist, which is itself the answer:
    Flyway has never run against this database.
    """
    exists = await session.execute(
        text(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = :schema AND c.relname = 'flyway_schema_history'"
        ),
        {"schema": _HISTORY_SCHEMA},
    )
    if exists.first() is None:
        return []

    rows = await session.execute(
        text(
            'SELECT "version", "description", "success", "installed_on" '  # noqa: S608 - schema is a module constant
            f"FROM {_HISTORY_SCHEMA}.flyway_schema_history "
            'WHERE "version" IS NOT NULL ORDER BY "installed_rank" DESC'
        )
    )
    return [
        {
            "version": row[0],
            "description": row[1],
            "success": bool(row[2]),
            "installed_on": row[3].isoformat() if row[3] is not None else None,
        }
        for row in rows.fetchall()
    ]


async def tenant_schema_drift(session: AsyncSession) -> list[dict[str, Any]]:
    """Per tenant schema, the columns ``public`` has that it does not.

    Reads ``pg_catalog`` rather than ``information_schema``. The latter is filtered by
    the connecting role's privileges, so a schema the role lacks ``USAGE`` on vanishes
    from the result entirely and reads as clean -- which is precisely the false negative
    this check exists to prevent. Verified against PostgreSQL: as an unprivileged role,
    ``information_schema.schemata`` omitted a drifted schema that ``pg_namespace``
    reported. ``pg_class``/``pg_attribute`` give the same independence for the columns.

    Only tables present in both schemas are compared. A table a tenant lacks entirely is
    a different problem -- it still falls through to ``public`` at query time -- and
    including it would drown the column signal.
    """
    drift_sql = """
        WITH public_cols AS (
            SELECT c.relname AS table_name, a.attname AS column_name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
        ),
        tenant_schemas AS (
            SELECT nspname FROM pg_namespace WHERE nspname ~ :pattern
        ),
        tenant_cols AS (
            SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname ~ :pattern AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
        ),
        tenant_tables AS (
            SELECT DISTINCT schema_name, table_name FROM tenant_cols
        )
        SELECT t.schema_name, p.table_name, p.column_name
        FROM tenant_tables t
        JOIN public_cols p ON p.table_name = t.table_name
        WHERE NOT EXISTS (
            SELECT 1 FROM tenant_cols tc
            WHERE tc.schema_name = t.schema_name
              AND tc.table_name = p.table_name
              AND tc.column_name = p.column_name
        )
        ORDER BY t.schema_name, p.table_name, p.column_name
    """
    rows = await session.execute(text(drift_sql), {"pattern": _TENANT_SCHEMA_PATTERN})
    by_schema: dict[str, list[str]] = {}
    for schema, table, column in rows.fetchall():
        by_schema.setdefault(schema, []).append(f"{table}.{column}")

    known = await session.execute(
        text("SELECT nspname FROM pg_namespace WHERE nspname ~ :pattern ORDER BY nspname"),
        {"pattern": _TENANT_SCHEMA_PATTERN},
    )
    return [{"schema": name, "missing": by_schema.get(name, [])} for (name,) in known.fetchall()]
