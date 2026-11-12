"""Postgres-backed checks that the write paths store association Name/Array (issue #1386).

V1.7 backfilled Name/Array for existing rows. Every path that creates an association now computes
them with lif.mdr_services.association_name, and the update paths recompute them when the
association or its child changes. Values are read back with column selects, so they come from the
database rather than the session's identity map.

Seed names are derived from the test name since the fixture DB is shared across the session.
"""

import pytest
from fastapi import HTTPException
from sqlmodel import select

from lif.mdr_dto.attribute_dto import UpdateAttributeDTO
from lif.mdr_dto.entity_association_dto import CreateEntityAssociationDTO, UpdateEntityAssociationDTO
from lif.mdr_dto.entity_attribute_association_dto import (
    CreateEntityAttributeAssociationDTO,
    UpdateEntityAttributeAssociationDTO,
)
from lif.mdr_dto.entity_dto import UpdateEntityDTO
from lif.mdr_dto.import_export_dto import CreateCloneDTO
from lif.mdr_sql_model.core import (
    Attribute,
    DataModel,
    DataModelType,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
)
from lif.mdr_services.association_name import entity_association_array, entity_association_name
from lif.mdr_services.attribute_service import update_attribute
from lif.mdr_services.entity_association_service import (
    create_entity_association,
    get_entity_association_by_id,
    update_entity_association,
)
from lif.mdr_services.entity_attribute_association_service import (
    create_entity_attribute_association,
    update_entity_attribute_association,
)
from lif.mdr_services.entity_service import update_entity
from lif.mdr_services.import_export_service import clone_datamodel
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

    # A Placement edit turns the embedded key into a reference key.
    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Placement="Reference"))
    assert await _entity_association(session, embedded_id) == ("enrolledInRefClass", False)

    # Pointing the association at another child takes that child's Name and Array.
    await update_entity_association(session, reference_id, UpdateEntityAssociationDTO(ChildEntityId=rows["course"].Id))
    assert await _entity_association(session, reference_id) == ("RefClass", False)


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


async def test_a_reference_is_single_even_when_its_child_is_a_list(test_db_session, request):
    """A Reference association's Array is false unless set some other way, whatever its child's (#1471)."""
    session = test_db_session
    _dm, rows, (embedded_id, reference_id, _attribute_association_id) = await _seed(session, request.node.name)

    # A new reference to a child whose Array is Yes.
    to_course = await create_entity_association(
        session,
        CreateEntityAssociationDTO(
            ParentEntityId=rows["course"].Id,
            ChildEntityId=rows["course"].Id,
            Relationship="prerequisite",
            Placement="Reference",
        ),
    )
    assert await _entity_association(session, to_course.Id) == ("prerequisiteRefCourse", False)

    # The child becoming a list leaves its reference single.
    organization_id = (await session.get(EntityAssociation, reference_id)).ChildEntityId
    await update_entity(session, organization_id, UpdateEntityDTO(Array="Yes"))
    assert await _entity_association(session, reference_id) == ("issuedByRefOrganization", False)

    # Turning a reference into an embedding gives it the child's Array, and back again.
    await update_entity_association(session, reference_id, UpdateEntityAssociationDTO(Placement="Embedded"))
    assert await _entity_association(session, reference_id) == ("issuedByOrganization", True)
    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Placement="Reference"))
    assert await _entity_association(session, embedded_id) == ("enrolledInRefCourse", False)


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
            entity_association_array(placement, child_array),
        )
    # A full export carries each association's Relationship, so every child keeps its key.
    assert sorted((row[4], row[5]) for row in entity_rows) == [
        ("enrolledInCourse", True),
        ("issuedByRefOrganization", False),
    ]
    assert [tuple(row) for row in attribute_rows.all()] == [("email", True)]


# Issue #1472: Name and Array set through the API on one association.


async def _other_model(session, tag):
    """A second data model with one entity and one attribute, for the cross-model guard."""
    dm = DataModel(
        Name=f"AssocNameOtherDM_{tag}",
        Type=DataModelType.SourceSchema,
        DataModelVersion="1.0",
        ContributorOrganization="UniconQA",
        Deleted=False,
    )
    session.add(dm)
    await session.commit()
    await session.refresh(dm)
    badge = Entity(Name="Badge", UniqueName="Badge", DataModelId=dm.Id, Array="No", Required="No", Deleted=False)
    nickname = Attribute(
        Name="nickname",
        UniqueName="Badge.nickname",
        DataModelId=dm.Id,
        DataType="xsd:string",
        Array="No",
        Deleted=False,
    )
    session.add_all([badge, nickname])
    await session.commit()
    await session.refresh(badge)
    await session.refresh(nickname)
    return dm, badge, nickname


async def _person_id(session, embedded_id):
    return (await session.get(EntityAssociation, embedded_id)).ParentEntityId


async def test_create_stores_a_sent_name_and_array(test_db_session, request):
    session = test_db_session
    dm, rows, (embedded_id, _reference_id, _attribute_association_id) = await _seed(session, request.node.name)
    person_id = await _person_id(session, embedded_id)
    phone = Attribute(
        Name="phone", UniqueName="Person.phone", DataModelId=dm.Id, DataType="xsd:string", Array="No", Deleted=False
    )
    session.add(phone)
    await session.commit()
    await session.refresh(phone)

    created = await create_entity_association(
        session,
        CreateEntityAssociationDTO(
            ParentEntityId=rows["course"].Id,
            ChildEntityId=rows["course"].Id,
            Relationship="prerequisite",
            Placement="Reference",
            Name="Prerequisites",
            Array=True,
        ),
    )
    assert (created.Name, created.Array) == ("Prerequisites", True)
    assert await _entity_association(session, created.Id) == ("Prerequisites", True)

    attribute_created = await create_entity_attribute_association(
        session, CreateEntityAttributeAssociationDTO(EntityId=person_id, AttributeId=phone.Id, Array=True)
    )
    # Name wasn't sent, so it's the rule's; Array was.
    assert (attribute_created.Name, attribute_created.Array) == ("phone", True)
    assert await _attribute_association(session, attribute_created.Id) == ("phone", True)


async def test_update_sets_name_and_array_and_later_edits_leave_them(test_db_session, request):
    session = test_db_session
    _dm, rows, (embedded_id, _reference_id, attribute_association_id) = await _seed(session, request.node.name)

    updated = await update_entity_association(
        session, embedded_id, UpdateEntityAssociationDTO(Name="Studies", Array=False)
    )
    assert (updated.Name, updated.Array) == ("Studies", False)
    await update_entity_attribute_association(
        session, attribute_association_id, UpdateEntityAttributeAssociationDTO(Name="contactEmail", Array=False)
    )

    # Edits to what the rule reads don't touch a value set here.
    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Relationship="takes"))
    await update_entity(session, rows["course"].Id, UpdateEntityDTO(Name="Class"))
    await update_attribute(session, rows["email"].Id, UpdateAttributeDTO(Name="emailAddress"))

    assert await _entity_association(session, embedded_id) == ("Studies", False)
    assert await _attribute_association(session, attribute_association_id) == ("contactEmail", False)
    # And a read returns them.
    association = await get_entity_association_by_id(session, embedded_id)
    assert (association.Name, association.Array) == ("Studies", False)


async def test_a_sent_value_holds_when_the_same_request_changes_the_rule(test_db_session, request):
    """A sent value equal to the old rule's isn't recomputed by a Relationship/Placement change beside it."""
    session = test_db_session
    _dm, _rows, (embedded_id, _reference_id, _attribute_association_id) = await _seed(session, request.node.name)

    await update_entity_association(
        session,
        embedded_id,
        UpdateEntityAssociationDTO(Relationship="takes", Placement="Reference", Name="enrolledInCourse", Array=True),
    )

    # A Reference that is a list (#1471), under the key it had before.
    assert await _entity_association(session, embedded_id) == ("enrolledInCourse", True)


async def test_a_sent_null_resets_to_the_rule(test_db_session, request):
    session = test_db_session
    _dm, _rows, (embedded_id, _reference_id, attribute_association_id) = await _seed(session, request.node.name)
    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Name="Studies", Array=False))
    await update_entity_attribute_association(
        session, attribute_association_id, UpdateEntityAttributeAssociationDTO(Name="contactEmail", Array=False)
    )

    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Name=None, Array=None))
    await update_entity_attribute_association(
        session, attribute_association_id, UpdateEntityAttributeAssociationDTO(Name=None, Array=None)
    )

    assert await _entity_association(session, embedded_id) == ("enrolledInCourse", True)
    assert await _attribute_association(session, attribute_association_id) == ("email", True)


@pytest.mark.parametrize("blank", ["", "   "])
async def test_a_blank_name_is_refused(test_db_session, request, blank):
    session = test_db_session
    _dm, rows, (embedded_id, _reference_id, attribute_association_id) = await _seed(session, request.node.name)

    with pytest.raises(HTTPException) as create_error:
        await create_entity_association(
            session,
            CreateEntityAssociationDTO(
                ParentEntityId=rows["course"].Id, ChildEntityId=rows["course"].Id, Placement="Reference", Name=blank
            ),
        )
    with pytest.raises(HTTPException) as update_error:
        await update_entity_attribute_association(
            session, attribute_association_id, UpdateEntityAttributeAssociationDTO(Name=blank)
        )

    assert create_error.value.status_code == update_error.value.status_code == 400
    assert "blank" in create_error.value.detail
    assert await _entity_association(session, embedded_id) == ("enrolledInCourse", True)
    assert await _attribute_association(session, attribute_association_id) == ("email", True)


async def test_name_and_array_are_refused_across_data_models(test_db_session, request):
    session = test_db_session
    _dm, _rows, (embedded_id, _reference_id, _attribute_association_id) = await _seed(session, request.node.name)
    person_id = await _person_id(session, embedded_id)
    _other, badge, nickname = await _other_model(session, request.node.name)

    with pytest.raises(HTTPException) as create_error:
        await create_entity_association(
            session, CreateEntityAssociationDTO(ParentEntityId=person_id, ChildEntityId=badge.Id, Name="Badges")
        )
    assert create_error.value.status_code == 400
    assert "different data models" in create_error.value.detail

    cross = await create_entity_association(
        session, CreateEntityAssociationDTO(ParentEntityId=person_id, ChildEntityId=badge.Id)
    )
    attribute_cross = await create_entity_attribute_association(
        session, CreateEntityAttributeAssociationDTO(EntityId=person_id, AttributeId=nickname.Id)
    )
    with pytest.raises(HTTPException) as entity_error:
        await update_entity_association(session, cross.Id, UpdateEntityAssociationDTO(Array=True))
    with pytest.raises(HTTPException) as attribute_error:
        await update_entity_attribute_association(
            session, attribute_cross.Id, UpdateEntityAttributeAssociationDTO(Name="alias")
        )
    assert entity_error.value.status_code == attribute_error.value.status_code == 400
    assert await _entity_association(session, cross.Id) == ("Badge", False)
    assert await _attribute_association(session, attribute_cross.Id) == ("nickname", False)

    # Edits that don't set Name or Array still work on the same rows.
    noted = await update_entity_association(session, cross.Id, UpdateEntityAssociationDTO(Notes="cross-model"))
    assert noted.Notes == "cross-model"
    await update_entity_attribute_association(
        session, attribute_cross.Id, UpdateEntityAttributeAssociationDTO(Notes="cross-model")
    )


async def test_name_and_array_are_refused_on_an_extension_association(test_db_session, request):
    session = test_db_session
    _dm, rows, (embedded_id, _reference_id, _attribute_association_id) = await _seed(session, request.node.name)
    person_id = await _person_id(session, embedded_id)
    extended_by, _badge, _nickname = await _other_model(session, request.node.name)

    with pytest.raises(HTTPException) as create_error:
        await create_entity_attribute_association(
            session,
            CreateEntityAttributeAssociationDTO(
                EntityId=rows["course"].Id,
                AttributeId=rows["email"].Id,
                ExtendedByDataModelId=extended_by.Id,
                Array=False,
            ),
        )
    assert create_error.value.status_code == 400
    assert "ExtendedByDataModelId" in create_error.value.detail

    extension = await create_entity_association(
        session,
        CreateEntityAssociationDTO(
            ParentEntityId=rows["course"].Id, ChildEntityId=person_id, ExtendedByDataModelId=extended_by.Id
        ),
    )
    with pytest.raises(HTTPException) as update_error:
        await update_entity_association(session, extension.Id, UpdateEntityAssociationDTO(Name="Students"))
    assert update_error.value.status_code == 400

    # Setting ExtendedByDataModelId in the same request is refused too.
    with pytest.raises(HTTPException) as same_request_error:
        await update_entity_association(
            session, embedded_id, UpdateEntityAssociationDTO(ExtendedByDataModelId=extended_by.Id, Array=False)
        )
    assert same_request_error.value.status_code == 400
    assert await _entity_association(session, embedded_id) == ("enrolledInCourse", True)


async def _schemas(session, data_model_id):
    schema = await generate_openapi_schema(session, data_model_id, include_attr_md=False, include_entity_md=False)
    return schema["components"]["schemas"]


async def test_the_generated_schema_follows_an_edited_name_and_array(test_db_session, request):
    session = test_db_session
    dm, _rows, (embedded_id, _reference_id, attribute_association_id) = await _seed(session, request.node.name)
    before = (await _schemas(session, dm.Id))["Person"]["properties"]
    assert before["enrolledInCourse"]["type"] == "array"
    assert before["email"]["type"] == "array"

    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Name="Studies", Array=False))
    await update_entity_attribute_association(
        session, attribute_association_id, UpdateEntityAttributeAssociationDTO(Array=False)
    )

    after = (await _schemas(session, dm.Id))["Person"]["properties"]
    assert "enrolledInCourse" not in after
    assert after["Studies"]["type"] == "object"
    assert after["email"]["type"] != "array"


async def test_a_clone_keeps_an_array_set_through_the_api(test_db_session, request):
    """Clone copies association Array (#1498). It recomputes Name, so a Name set here is lost (#1500)."""
    session = test_db_session
    dm, _rows, (embedded_id, _reference_id, attribute_association_id) = await _seed(session, request.node.name)
    await update_entity_association(session, embedded_id, UpdateEntityAssociationDTO(Array=False))
    await update_entity_attribute_association(
        session, attribute_association_id, UpdateEntityAttributeAssociationDTO(Array=False)
    )

    clone = await clone_datamodel(
        session,
        CreateCloneDTO(
            source_data_model_id=dm.Id,
            data_model_name=f"Clone of {dm.Name}",
            data_model_type=DataModelType.SourceSchema,
            data_model_version="1.0",
        ),
    )
    await session.commit()

    properties = (await _schemas(session, clone.Id))["Person"]["properties"]
    assert properties["enrolledInCourse"]["type"] == "object"
    assert properties["email"]["type"] != "array"
