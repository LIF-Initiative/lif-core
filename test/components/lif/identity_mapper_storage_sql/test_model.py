"""
Guards for the `idx_org_person` index added in #1231.

`uq_identity_mapping` is 3460 bytes over four utf8mb4 columns, past InnoDB's 3072-byte
B-tree key limit, so MariaDB silently degrades it to `USING HASH` and the optimizer can
never use it -- every `read_by_lif_org_and_person` was a full table scan. `idx_org_person`
is the usable B-tree that serves that read.

These tests run on SQLite, which has no such key limit, so they cannot detect the HASH
degradation itself -- only MariaDB can, via `SHOW INDEX` on a populated table. What they do
guard is the pair of things that broke here: that an index covering the read's filter
columns exists and the planner picks it, and that the model has not drifted from the
production DDL (a divergence already found once, as the "5 unused indexes" P2 in #1178).
"""

import re
from pathlib import Path

from sqlalchemy import event

from lif.identity_mapper_storage_sql import crud
from lif.identity_mapper_storage_sql.model import IdentityMappingModel

DDL_PATH = Path(__file__).parents[4] / "projects" / "lif_identity_mapper_mariadb" / "02-ddl.sql"

INDEX_NAME = "idx_org_person"
INDEX_COLUMNS = ["lif_organization_id", "lif_organization_person_id"]


def _model_index_columns(name: str) -> list[str]:
    index = next(i for i in IdentityMappingModel.__table__.indexes if i.name == name)
    return [c.name for c in index.columns]


def _ddl_index_columns(name: str) -> list[str]:
    match = re.search(rf"INDEX\s+{name}\s*\(([^)]*)\)", DDL_PATH.read_text())
    assert match, f"{name} is not declared in {DDL_PATH.name}"
    return [c.strip() for c in match.group(1).split(",")]


def _statement_emitted_by_the_org_and_person_read(session) -> str:
    """The SQL `read_by_lif_org_and_person` actually emits, captured rather than restated."""
    captured: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        crud.read_by_lif_org_and_person(session, "org-1", "person-1")
    finally:
        event.remove(engine, "before_cursor_execute", record)

    selects = [s for s in captured if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1, captured
    return selects[0]


def test_planner_uses_the_index_for_the_org_and_person_read(session):
    """
    The read the index exists for must actually resolve through it, not a table scan.

    The statement is taken from the production code path rather than written out here, so
    changing what `read_by_lif_org_and_person` filters on re-points this test at the new
    query instead of silently leaving it passing against the old one.
    """
    statement = _statement_emitted_by_the_org_and_person_read(session)
    # Driver-level: the captured statement carries the driver's own positional placeholders.
    rows = session.connection().exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", ("org-1", "person-1"))
    plan = "\n".join(str(row) for row in rows)
    assert f"USING INDEX {INDEX_NAME}" in plan, plan
    assert "SCAN identity_mappings" not in plan, plan


def test_model_index_matches_the_production_ddl():
    """
    The model only builds tables under IDENTITY_MAPPER_DB_AUTO_CREATE_TABLES; 02-ddl.sql is
    what production runs. They have to agree, or the index verified against one is absent
    from the other.
    """
    assert _model_index_columns(INDEX_NAME) == INDEX_COLUMNS
    assert _ddl_index_columns(INDEX_NAME) == INDEX_COLUMNS


def test_index_covers_every_column_the_read_filters_on(session):
    """
    Order is load-bearing: the index serves this read as a leftmost prefix. If the read
    grows a third filter column or reorders the two, the index stops covering it -- and on
    MariaDB a third column would also push the key past the 3072-byte limit.
    """
    statement = _statement_emitted_by_the_org_and_person_read(session)
    filtered = re.findall(r"identity_mappings\.(\w+) = ", statement)
    assert filtered == INDEX_COLUMNS, statement
