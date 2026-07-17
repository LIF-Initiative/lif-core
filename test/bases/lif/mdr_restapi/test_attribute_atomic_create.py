"""Atomic create-attribute (Issue #1028).

Passing ``EntityId`` to ``create_attribute`` must create the attribute AND its
entity association in a single transaction, so a dropped response can never leave
an orphaned (persisted-but-unassociated) attribute. Without ``EntityId`` the
behaviour is unchanged (attribute only). If either step fails, the whole create
rolls back — never a half-created attribute.

Drives the real service against a live Postgres (``test_db_session`` fixture).
Seed names are derived from the test name (``request.node.name``) since the
fixture DB is shared across tests in this module.
"""

import pytest
from fastapi import HTTPException
from sqlmodel import select

from lif.datatypes.mdr_sql_model import Attribute, DataModel, DataModelType, Entity, EntityAttributeAssociation
from lif.mdr_dto.attribute_dto import CreateAttributeDTO
from lif.mdr_services import attribute_service
from lif.mdr_services.attribute_service import create_attribute


async def _seed_model_and_entity(session, tag):
    dm = DataModel(
        Name=f"AtomicCreateDM_{tag}",
        Type=DataModelType.SourceSchema,
        DataModelVersion="1.0",
        ContributorOrganization="Test Organization",
        Deleted=False,
    )
    session.add(dm)
    await session.commit()
    await session.refresh(dm)

    name = f"Widget_{tag}"
    entity = Entity(Name=name, UniqueName=name, DataModelId=dm.Id, Array="No", Required="No", Deleted=False)
    session.add(entity)
    await session.commit()
    await session.refresh(entity)
    return dm, entity


async def _associations_for(session, attribute_id):
    result = await session.execute(
        select(EntityAttributeAssociation).where(
            EntityAttributeAssociation.AttributeId == attribute_id,
            EntityAttributeAssociation.Deleted == False,  # noqa: E712
        )
    )
    return result.scalars().all()


async def _attributes_named(session, unique_name):
    result = await session.execute(select(Attribute).where(Attribute.UniqueName == unique_name))
    return result.scalars().all()


async def test_create_attribute_with_entity_id_creates_association_atomically(test_db_session, request):
    session = test_db_session
    dm, entity = await _seed_model_and_entity(session, request.node.name)

    created = await create_attribute(
        session,
        CreateAttributeDTO(
            Name="color",
            UniqueName=f"{entity.UniqueName}.color",
            DataType="xsd:string",
            DataModelId=dm.Id,
            EntityId=entity.Id,
        ),
    )

    assert created.Id is not None
    # The association was created in the same call — the attribute is NOT orphaned.
    assocs = await _associations_for(session, created.Id)
    assert len(assocs) == 1
    assert assocs[0].EntityId == entity.Id


async def test_create_attribute_without_entity_id_makes_no_association(test_db_session, request):
    """Backward-compatible: no EntityId -> attribute only, no association (unchanged behaviour)."""
    session = test_db_session
    dm, _entity = await _seed_model_and_entity(session, request.node.name)

    created = await create_attribute(
        session,
        CreateAttributeDTO(
            Name="size", UniqueName=f"{_entity.UniqueName}.size", DataType="xsd:string", DataModelId=dm.Id
        ),
    )

    assert created.Id is not None
    assert await _associations_for(session, created.Id) == []


async def test_failure_creating_attribute_creates_no_association(test_db_session, request):
    """If the attribute step fails (duplicate unique name), the failed attempt creates no association."""
    session = test_db_session
    dm, entity = await _seed_model_and_entity(session, request.node.name)
    dto = CreateAttributeDTO(
        Name="dup", UniqueName=f"{entity.UniqueName}.dup", DataType="xsd:string", DataModelId=dm.Id, EntityId=entity.Id
    )

    first = await create_attribute(session, dto)  # succeeds (attribute + association)

    # A second create with the same unique name fails the uniqueness check.
    with pytest.raises(HTTPException) as exc:
        await create_attribute(session, dto)
    assert exc.value.status_code == 400

    # Only the first attribute's association exists — the failed retry added nothing.
    result = await session.execute(
        select(EntityAttributeAssociation).where(
            EntityAttributeAssociation.EntityId == entity.Id,
            EntityAttributeAssociation.Deleted == False,  # noqa: E712
        )
    )
    assocs = result.scalars().all()
    assert len(assocs) == 1
    assert assocs[0].AttributeId == first.Id


async def test_failure_creating_association_rolls_back_the_attribute(test_db_session, request, monkeypatch):
    """If the association step fails, the attribute must roll back too — no orphaned attribute."""
    session = test_db_session
    dm, entity = await _seed_model_and_entity(session, request.node.name)

    class _BoomAssociation:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("simulated association-creation failure")

    monkeypatch.setattr(attribute_service, "EntityAttributeAssociation", _BoomAssociation)

    unique_name = f"{entity.UniqueName}.rollback"
    with pytest.raises(RuntimeError):
        await create_attribute(
            session,
            CreateAttributeDTO(
                Name="rollback", UniqueName=unique_name, DataType="xsd:string", DataModelId=dm.Id, EntityId=entity.Id
            ),
        )

    # The attribute must NOT have persisted — it was rolled back with the failed association.
    assert await _attributes_named(session, unique_name) == []
