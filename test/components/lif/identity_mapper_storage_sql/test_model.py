"""
Guards for `uq_identity_mapping`, the composite unique key that also serves the org/person read.

Before #1258 its four utf8mb4 key columns totalled 3460 bytes, past InnoDB's 3072-byte
B-tree key limit, so MariaDB silently degraded it to `USING HASH` and the optimizer could
never read through it (#1231), while MySQL 8 rejected the DDL outright. Narrowing three of
the columns to 191 makes it a real B-tree, which serves `read_by_lif_org_and_person` as a
leftmost prefix -- so the separate `idx_org_person` #1231 added is gone.

These tests run on SQLite, which has no such key limit, so they cannot observe the HASH
degradation itself -- only MariaDB can, via `SHOW INDEX` on a populated table. What they do
guard is everything that has to stay true for it not to come back: the key's byte width,
the model agreeing with the production DDL (a divergence already found once, as the
"5 unused indexes" P2 in #1178), and the read's filter columns leading the key.
"""

import re
from pathlib import Path

from sqlalchemy import UniqueConstraint, event

from lif.identity_mapper_storage_sql import crud
from lif.identity_mapper_storage_sql.model import IdentityMappingModel

DDL_PATH = Path(__file__).parents[4] / "projects" / "lif_identity_mapper_mariadb" / "02-ddl.sql"

KEY_NAME = "uq_identity_mapping"
KEY_COLUMNS = ["lif_organization_id", "lif_organization_person_id", "target_system_id", "target_system_person_id_type"]
READ_COLUMNS = KEY_COLUMNS[:2]

# InnoDB's B-tree key limit, and the worst-case bytes per character under utf8mb4.
INNODB_MAX_KEY_BYTES = 3072
UTF8MB4_BYTES_PER_CHAR = 4


def _model_key_columns() -> list[str]:
    constraint = next(
        c for c in IdentityMappingModel.__table__.constraints if isinstance(c, UniqueConstraint) and c.name == KEY_NAME
    )
    return [c.name for c in constraint.columns]


def _ddl_key_columns() -> list[str]:
    match = re.search(rf"CONSTRAINT\s+{KEY_NAME}\s+UNIQUE\s*\(([^)]*)\)", DDL_PATH.read_text())
    assert match, f"{KEY_NAME} is not declared in {DDL_PATH.name}"
    return [c.strip() for c in match.group(1).split(",")]


def _model_widths() -> dict[str, int]:
    return {c.name: c.type.length for c in IdentityMappingModel.__table__.columns}


def _ddl_widths() -> dict[str, int]:
    return {name: int(width) for name, width in re.findall(r"^\s*(\w+)\s+VARCHAR\((\d+)\)", DDL_PATH.read_text(), re.M)}


async def _statement_emitted_by_the_org_and_person_read(session) -> str:
    """The SQL `read_by_lif_org_and_person` actually emits, captured rather than restated."""
    captured: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        await crud.read_by_lif_org_and_person(session, "org-1", "person-1")
    finally:
        event.remove(engine, "before_cursor_execute", record)

    selects = [s for s in captured if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1, captured
    return selects[0]


def test_unique_key_fits_the_innodb_btree_limit():
    """
    The guard that would have caught #1231. Over 3072 bytes MariaDB builds the key as HASH
    with no error and MySQL 8 refuses the table, and SQLite accepts either, so a widened
    column is invisible to every other test here.
    """
    widths = _ddl_widths()
    key_bytes = sum(widths[c] for c in _ddl_key_columns()) * UTF8MB4_BYTES_PER_CHAR
    assert key_bytes <= INNODB_MAX_KEY_BYTES, f"{KEY_NAME} is {key_bytes} bytes"


def test_model_key_matches_the_production_ddl():
    """
    The model only builds tables under IDENTITY_MAPPER_DB_AUTO_CREATE_TABLES; 02-ddl.sql is
    what production runs. They have to agree on the key and on the widths that size it, or
    the key verified against one is not the key in the other.
    """
    assert _model_key_columns() == KEY_COLUMNS
    assert _ddl_key_columns() == KEY_COLUMNS
    model_widths, ddl_widths = _model_widths(), _ddl_widths()
    assert {c: model_widths[c] for c in KEY_COLUMNS} == {c: ddl_widths[c] for c in KEY_COLUMNS}


def test_model_and_ddl_declare_the_same_secondary_indexes():
    """Neither side may carry an index the other lacks -- the #1178 drift, in either direction."""
    model_indexes = {i.name for i in IdentityMappingModel.__table__.indexes}
    ddl_indexes = set(re.findall(r"^\s*INDEX\s+(\w+)", DDL_PATH.read_text(), re.M))
    assert model_indexes == ddl_indexes


async def test_planner_uses_an_index_for_the_org_and_person_read(session):
    """
    The read must resolve through an index, not a table scan. The only other index is the
    primary key on mapping_id, which cannot serve this filter, so an index lookup here is
    the unique key's leftmost prefix.

    The statement is taken from the production code path rather than written out here, so
    changing what `read_by_lif_org_and_person` filters on re-points this test at the new
    query instead of silently leaving it passing against the old one.
    """
    statement = await _statement_emitted_by_the_org_and_person_read(session)
    # Driver-level: the captured statement carries the driver's own positional placeholders.
    connection = await session.connection()
    rows = await connection.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", ("org-1", "person-1"))
    plan = "\n".join(str(row) for row in rows)
    assert "USING INDEX" in plan, plan
    assert "SCAN identity_mappings" not in plan, plan


async def test_read_filters_on_the_leading_columns_of_the_key(session):
    """
    Order is load-bearing: the unique key serves this read only as a leftmost prefix. If the
    read reorders its filters or filters on anything but the key's first two columns, the
    key stops covering it and every lookup scans again.
    """
    statement = await _statement_emitted_by_the_org_and_person_read(session)
    filtered = re.findall(r"identity_mappings\.(\w+) = ", statement)
    assert filtered == READ_COLUMNS, statement
