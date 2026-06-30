"""End-to-end round-trip test for entity references (Issue #756).

Drives both halves of the real pipeline against a live Postgres database:

    seed a source model with a Reference association
        -> generate_openapi_schema  (the export the UI/API hands back)
        -> create_data_model_from_openapi_schema  (the create-by-upload import)

and asserts the reference survives the trip — i.e. the generator's inlined
"<relationship>Ref<Child>" property is understood by the upload reader, recreated
as a Reference-placement EntityAssociation, and NOT materialized as a bogus child
entity. Before #756 the reference was silently dropped on upload.
"""

from sqlmodel import select

from lif.datatypes.mdr_sql_model import DataModel, DataModelType, Entity, EntityAssociation, EntityPlacementType
from lif.mdr_services.schema_generation_service import generate_openapi_schema
from lif.mdr_services.schema_upload_service import create_data_model_from_openapi_schema


async def _seed_source_model(session):
    """A minimal source model: Person --issuedBy(Reference)--> Organization."""
    dm = DataModel(
        Name="RoundTripSource",
        Type=DataModelType.SourceSchema,
        DataModelVersion="1.0",
        ContributorOrganization="UniconQA",
        Deleted=False,
    )
    session.add(dm)
    await session.commit()
    await session.refresh(dm)

    person = Entity(Name="Person", UniqueName="Person", DataModelId=dm.Id, Array="No", Required="No", Deleted=False)
    org = Entity(
        Name="Organization", UniqueName="Organization", DataModelId=dm.Id, Array="No", Required="No", Deleted=False
    )
    session.add(person)
    session.add(org)
    await session.commit()
    await session.refresh(person)
    await session.refresh(org)

    assoc = EntityAssociation(
        ParentEntityId=person.Id,
        ChildEntityId=org.Id,
        Relationship="issuedBy",
        Placement=EntityPlacementType.Reference,
        Deleted=False,
    )
    session.add(assoc)
    await session.commit()
    return dm


async def test_reference_survives_generate_then_upload(test_db_session):
    session = test_db_session
    source_dm = await _seed_source_model(session)

    # --- export: the schema the generator produces for the source model ---
    schema = await generate_openapi_schema(session, source_dm.Id, include_attr_md=True, include_entity_md=True)
    person_props = schema["components"]["schemas"]["Person"]["properties"]
    # The reference is inlined under a "Ref"-infix key, not emitted as a "$ref".
    assert "issuedByRefOrganization" in person_props
    assert "$ref" not in person_props["issuedByRefOrganization"]

    # --- import: round-trip that schema back in through create-by-upload ---
    target = await create_data_model_from_openapi_schema(
        session=session,
        openapi_schema=schema,
        data_model_name="RoundTripTarget",
        data_model_version="1.0",
        data_model_type="SourceSchema",
        data_model_description=None,
        base_data_model_id=None,
        use_considerations=None,
        notes=None,
        activation_date=None,
        deprecation_date=None,
        contributor=None,
        contributor_organization="UniconQA",
    )

    # The reference must NOT have been materialized as a child entity.
    entities = (
        (await session.execute(select(Entity).where(Entity.DataModelId == target.Id, Entity.Deleted == False)))
        .scalars()
        .all()
    )
    names = sorted(e.Name for e in entities)
    assert names == ["Organization", "Person"], names
    assert not any("Ref" in n for n in names)

    # The reference association must have been recreated, parent->child, with its relationship.
    by_name = {e.Name: e.Id for e in entities}
    assocs = (
        (
            await session.execute(
                select(EntityAssociation)
                .join(Entity, Entity.Id == EntityAssociation.ParentEntityId)
                .where(Entity.DataModelId == target.Id, EntityAssociation.Deleted == False)
            )
        )
        .scalars()
        .all()
    )
    references = [a for a in assocs if a.Placement == EntityPlacementType.Reference]
    assert len(references) == 1, [(a.Placement, a.Relationship) for a in assocs]
    ref = references[0]
    assert ref.ParentEntityId == by_name["Person"]
    assert ref.ChildEntityId == by_name["Organization"]
    assert ref.Relationship == "issuedBy"
