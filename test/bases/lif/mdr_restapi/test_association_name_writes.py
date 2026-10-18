"""Postgres-backed checks that the write paths store association Name/Array (issue #1386).

V1.7 backfilled Name/Array for existing rows. Every path that creates an association now computes
them with lif.mdr_services.association_name, and the update paths recompute them when the
association or its child changes. Values are read back with column selects, so they come from the
database rather than the session's identity map.

Seed names are derived from the test name since the fixture DB is shared across the session.
"""

from sqlmodel import select

from lif.mdr_dto.attribute_dto import UpdateAttributeDTO
from lif.mdr_dto.entity_association_dto import CreateEntityAssociationDTO, UpdateEntityAssociationDTO
from lif.mdr_dto.entity_attribute_association_dto import CreateEntityAttributeAssociationDTO
from lif.mdr_dto.entity_dto import UpdateEntityDTO
from lif.mdr_sql_model.core import (
    Attribute,
    DataModel,
    DataModelType,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
)
from lif.mdr_services.association_name import association_array, entity_association_name
from lif.mdr_services.attribute_service import update_attribute
from lif.mdr_services.entity_association_service import create_entity_association, update_entity_association
from lif.mdr_services.entity_attribute_association_service import create_entity_attribute_association
from lif.mdr_services.entity_service import update_entity
from lif.mdr_services.schema_generation_service import generate_openapi_schema
from lif.mdr_services.schema_upload_service import create_data_model_from_openapi_schema


async def _seed(session, tag):
    """Person embeds Course (enrolledIn), references Organization (issuedBy), and has an email list."""
    dm = DataModel(
        Name=f"AssocNameDM_{tag}",
        Type=DataModelType.SourceSchema,
        DataModelVersion="1.0",
        ContributorOrganization="UniconQA",
        Deleted=False,
    )
    session.add(dm)
    await session.commit()
    await session.refresh(dm)

    def entity(name, array):
        return Entity(Name=name, UniqueName=name, DataModelId=dm.Id, Array=array, Required="No", Deleted=False)

    person, course, org = entity("Person", "No"), entity("Course", "Yes"), entity("Organization", "No")
    email = Attribute(
        Name="email", UniqueName="Person.email", DataModelId=dm.Id, DataType="xsd:string", Array="Yes", Deleted=False
    )
    session.add_all([person, course, org, email])
    await session.commit()
    for row in (person, course, org, email):
        await session.refresh(row)

    embedded = await create_entity_association(
        session,
        CreateEntityAssociationDTO(
            ParentEntityId=person.Id, ChildEntityId=course.Id, Relationship="enrolledIn", Placement="Embedded"
        ),
    )
    reference = await create_entity_association(
        session,
        CreateEntityAssociationDTO(
            ParentEntityId=person.Id, ChildEntityId=org.Id, Relationship="issuedBy", Placement="Reference"
        ),
    )
    attribute_association = await create_entity_attribute_association(
        session, CreateEntityAttributeAssociationDTO(EntityId=person.Id, AttributeId=email.Id)
    )
    return dm, {"course": course, "email": email}, (embedded.Id, reference.Id, attribute_association.Id)


async def _entity_association(session, association_id):
    result = await session.execute(
        select(EntityAssociation.Name, EntityAssociation.Array).where(EntityAssociation.Id == association_id)
    )
    return tuple(result.one())


async def _attribute_association(session, association_id):
    result = await session.execute(
        select(EntityAttributeAssociation.Name, EntityAttributeAssociation.Array).where(
            EntityAttributeAssociation.Id == association_id
        )
    )
    return tuple(result.one())


async def test_create_paths_store_name_and_array(test_db_session, request):
    session = test_db_session
    _dm, _rows, (embedded_id, reference_id, attribute_association_id) = await _seed(session, request.node.name)

    assert await _entity_association(session, embedded_id) == ("enrolledInCourse", True)
    assert await _entity_association(session, reference_id) == ("issuedByRefOrganization", False)
    assert await _attribute_association(session, attribute_association_id) == ("email", True)


async def test_update_paths_recompute_name_and_array(test_db_session, request):
    session = test_db_session
    _dm, rows, (embedded_id, reference_id, attribute_association_id) = await _seed(session, request.node.name)

    # Renaming the child, or changing its Array, changes the key and list-ness it has under Person.
    await update_entity(session, rows["course"].Id, UpdateEntityDTO(Name="Class", Array="No"))
    assert await _entity_association(session, embedded_id) == ("enrolledInClass", False)

    await update_attribute(session, rows["email"].Id, UpdateAttributeDTO(Name="emailAddress"))
    assert await _attribute_association(session, attribute_association_id) == ("emailAddress", True)

    # A Relationship edit on the association itself; a structural has* name collapses to the bare child.
    await update_entity_association(session, reference_id, UpdateEntityAssociationDTO(Relationship="hasIssuer"))
    assert await _entity_association(session, reference_id) == ("RefOrganization", False)


async def test_update_paths_leave_values_that_did_not_come_from_the_rule(test_db_session, request):
    """A Name/Array written some other way (as a model import or #1388 will) survives later edits."""
    session = test_db_session
    _dm, rows, (embedded_id, reference_id, attribute_association_id) = await _seed(session, request.node.name)
    # Set the stored values directly, as an import writes them from a file.
    for model, association_id, values in (
        (EntityAssociation, embedded_id, {"Name": "Studies", "Array": False}),
        (EntityAttributeAssociation, attribute_association_id, {"Name": "contactEmail", "Array": False}),
    ):
        row = await session.get(model, association_id)
        for key, value in values.items():
            setattr(row, key, value)
        session.add(row)
    await session.commit()

    await update_entity(session, rows["course"].Id, UpdateEntityDTO(Name="Class", Array="No"))
    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Relationship="takes"))
    await update_attribute(session, rows["email"].Id, UpdateAttributeDTO(Name="emailAddress", Array="No"))

    assert await _entity_association(session, embedded_id) == ("Studies", False)
    assert await _attribute_association(session, attribute_association_id) == ("contactEmail", False)
    # The reference under the same parent still came from the rule, so it still follows an edit.
    await update_entity_association(session, reference_id, UpdateEntityAssociationDTO(Relationship="hasIssuer"))
    assert await _entity_association(session, reference_id) == ("RefOrganization", False)


async def test_upload_stores_the_key_each_child_was_uploaded_under(test_db_session, request):
    session = test_db_session
    source, _rows, _ids = await _seed(session, request.node.name)
    schema = await generate_openapi_schema(
        session, source.Id, include_attr_md=True, include_entity_md=True, full_export=True
    )

    target = await create_data_model_from_openapi_schema(
        session=session,
        openapi_schema=schema,
        data_model_name=f"{source.Name}_uploaded",
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

    child = Entity.__table__.alias("child")
    entity_rows = await session.execute(
        select(
            EntityAssociation.Relationship,
            EntityAssociation.Placement,
            child.c.Name,
            child.c.Array,
            EntityAssociation.Name,
            EntityAssociation.Array,
        )
        .join(Entity, Entity.Id == EntityAssociation.ParentEntityId)
        .join(child, child.c.Id == EntityAssociation.ChildEntityId)
        .where(Entity.DataModelId == target.Id)
    )
    entity_rows = entity_rows.all()
    attribute_rows = await session.execute(
        select(EntityAttributeAssociation.Name, EntityAttributeAssociation.Array)
        .join(Entity, Entity.Id == EntityAttributeAssociation.EntityId)
        .where(Entity.DataModelId == target.Id)
    )

    assert len(entity_rows) == 2
    for relationship, placement, child_name, child_array, name, array in entity_rows:
        assert (name, array) == (
            entity_association_name(relationship, placement, child_name),
            association_array(child_array),
        )
    # A full export carries each association's Relationship, so every child keeps its key.
    assert sorted((row[4], row[5]) for row in entity_rows) == [
        ("enrolledInCourse", True),
        ("issuedByRefOrganization", False),
    ]
    assert [tuple(row) for row in attribute_rows.all()] == [("email", True)]
