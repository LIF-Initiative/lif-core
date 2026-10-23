"""Postgres-backed checks that the V1.7 columns and the Python rules agree (issue #1386).

V1.7 backfills association Name/Array in SQL, and the create paths will compute them with
lif.mdr_services.association_name. backup.sql (loaded by conftest's postgres_server) holds V1.7's
result, so every stored value must equal what the Python rule gives for the same row.

Only rows with a Name are judged: other tests in the session insert associations directly, bypassing
the services that compute Name (test_association_name_writes.py covers those services).
"""

import pytest
from sqlmodel import select

from lif.mdr_services.association_name import association_array, entity_association_name
from lif.mdr_services.schema_generation_service import ENTITY_FIELDS_NOT_EMITTED, generate_openapi_schema
from lif.mdr_sql_model.core import (
    AccessType,
    Attribute,
    DataModel,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
)

SEED_SCHEMAS = ("public", "tenant_lif_team")
# Well under the seed's counts (each schema holds 170+ entity and 2,200+ attribute associations), so
# the checks can't pass on a handful of rows.
MIN_ROWS = 100


@pytest.mark.parametrize("schema", SEED_SCHEMAS)
def test_stored_entity_association_name_and_array_match_the_python_rule(pg_conn, schema):
    with pg_conn.cursor() as cur:
        cur.execute(
            f'SELECT ea."Id", ea."Relationship", ea."Placement", c."Name", c."Array", ea."Name", ea."Array" '
            f'FROM "{schema}"."EntityAssociation" ea JOIN "{schema}"."Entities" c ON c."Id" = ea."ChildEntityId" '
            'WHERE ea."Name" IS NOT NULL'
        )
        rows = cur.fetchall()
    assert len(rows) >= MIN_ROWS
    mismatches = [
        row
        for row in rows
        if (row[5], row[6]) != (entity_association_name(row[1], row[2], row[3]), association_array(row[4]))
    ]
    assert mismatches == []


@pytest.mark.parametrize("schema", SEED_SCHEMAS)
def test_stored_attribute_association_name_and_array_match_the_python_rule(pg_conn, schema):
    with pg_conn.cursor() as cur:
        cur.execute(
            f'SELECT x."Id", a."Name", a."Array", x."Name", x."Array" FROM "{schema}"."EntityAttributeAssociation" x '
            f'JOIN "{schema}"."Attributes" a ON a."Id" = x."AttributeId" WHERE x."Name" IS NOT NULL'
        )
        rows = cur.fetchall()
    assert len(rows) >= MIN_ROWS
    mismatches = [row for row in rows if (row[3], row[4]) != (row[1], association_array(row[2]))]
    assert mismatches == []


async def test_models_read_the_new_columns(test_db_session):
    # An element whose flags V1.7 took from its model's own inclusion row (models 17 and 18).
    entity = (
        (await test_db_session.execute(select(Entity).where(Entity.LevelOfAccess != AccessType.Public).limit(1)))
        .scalars()
        .first()
    )
    assert entity is not None
    assert isinstance(entity.LevelOfAccess, AccessType)
    assert isinstance(entity.Queryable, bool) and isinstance(entity.Modifiable, bool)

    attribute = (await test_db_session.execute(select(Attribute).limit(1))).scalars().first()
    assert isinstance(attribute.LevelOfAccess, AccessType)

    association = (await test_db_session.execute(select(EntityAssociation).limit(1))).scalars().first()
    assert association.Name and isinstance(association.Array, bool)
    attribute_association = (
        (await test_db_session.execute(select(EntityAttributeAssociation).limit(1))).scalars().first()
    )
    assert attribute_association.Name and isinstance(attribute_association.Array, bool)

    data_model = (await test_db_session.execute(select(DataModel).limit(1))).scalars().first()
    assert data_model.CopiedFromName is None  # Not backfilled until #1388.


async def test_new_rows_get_the_column_defaults(test_db_session):
    data_model_id = (await test_db_session.execute(select(DataModel.Id).limit(1))).scalars().first()
    entity = Entity(Name="PrBProbe", UniqueName="PrBProbe", DataModelId=data_model_id)
    test_db_session.add(entity)
    await test_db_session.flush()
    await test_db_session.refresh(entity)
    assert (entity.LevelOfAccess, entity.Queryable, entity.Modifiable) == (AccessType.Public, False, False)

    association = EntityAssociation(ParentEntityId=entity.Id, ChildEntityId=entity.Id)
    test_db_session.add(association)
    await test_db_session.flush()
    await test_db_session.refresh(association)
    # NULL until a create path computes it (it marks rows a later backfill still has to fill).
    assert (association.Name, association.Array) == (None, None)
    await test_db_session.rollback()


def _keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value)


async def test_generated_schema_leaves_out_the_new_entity_fields(test_db_session):
    # The generator copies each entity's fields when include_entity_md is set. Emitting the V1.7 flags is
    # #1395's change, so until then they must not appear (model 1 covers both of the generator's copy sites).
    schema = await generate_openapi_schema(test_db_session, 1, include_attr_md=True, include_entity_md=True)
    keys = set(_keys(schema))
    assert "UniqueName" in keys  # Entity metadata was emitted, so the check below can fail.
    assert keys & ENTITY_FIELDS_NOT_EMITTED == set()
