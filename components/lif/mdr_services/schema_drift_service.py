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

# Schemas that are never tenants and should not be compared against public.
_NON_TENANT_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast", "public")

# The schema Flyway records its history in. Flyway writes this table into its own
# default schema, which for this stack is public.
_HISTORY_SCHEMA = "public"


async def applied_migrations(session: AsyncSession) -> list[dict[str, Any]]:
    """Every row of ``flyway_schema_history``, newest first.

    Returns an empty list when the table does not exist, which is itself the
    answer: Flyway has never run against this database.
    """
    exists = await session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = 'flyway_schema_history'"
        ),
        {"schema": _HISTORY_SCHEMA},
    )
    if exists.first() is None:
        return []

    rows = await session.execute(
        text(
            f'SELECT "version", "description", "success", "installed_on" '  # noqa: S608 - schema is a module constant
            f"FROM {_HISTORY_SCHEMA}.flyway_schema_history "
            f'WHERE "version" IS NOT NULL ORDER BY "installed_rank" DESC'
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
    """Per non-public schema, the columns ``public`` has that it does not.

    A tenant schema is a clone of ``public`` taken when the tenant was created, so
    any column a later migration added to ``public`` is absent there. Only tables
    present in both schemas are compared -- a table the tenant does not have at all
    is a different problem (it still falls through to public at query time) and
    would drown this signal.

    Reports one entry per schema, with ``missing`` empty when it is current.
    """
    excluded = ", ".join(f"'{name}'" for name in _NON_TENANT_SCHEMAS)
    drift_sql = f"""
        WITH public_cols AS (
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
        ),
        other_schemas AS (
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ({excluded})
              AND schema_name NOT LIKE 'pg\\_%'
        )
        SELECT o.schema_name, p.table_name, p.column_name
        FROM other_schemas o
        JOIN public_cols p ON TRUE
        JOIN information_schema.tables it
          ON it.table_schema = o.schema_name AND it.table_name = p.table_name
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns c
            WHERE c.table_schema = o.schema_name
              AND c.table_name = p.table_name
              AND c.column_name = p.column_name
        )
        ORDER BY o.schema_name, p.table_name, p.column_name
    """  # noqa: S608 - interpolation is a module constant, never request input

    rows = await session.execute(text(drift_sql))
    by_schema: dict[str, list[str]] = {}
    for schema, table, column in rows.fetchall():
        by_schema.setdefault(schema, []).append(f"{table}.{column}")

    known = await session.execute(
        text(
            f"SELECT schema_name FROM information_schema.schemata "  # noqa: S608 - same constant
            f"WHERE schema_name NOT IN ({excluded}) AND schema_name NOT LIKE 'pg\\_%' "
            f"ORDER BY schema_name"
        )
    )
    return [{"schema": name, "missing": by_schema.get(name, [])} for (name,) in known.fetchall()]
