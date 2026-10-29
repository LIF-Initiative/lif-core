"""Postgres-backed checks that a self-contained OrgLIF reads its own rows (issue #1388 P1).

Converting an overlay (17, 18) clears its BaseDataModelId and inclusion rows but keeps its stored Type.
The services used to branch on that Type, so a converted model was sent down the overlay path: looking
up a base model it no longer has, or filtering through inclusion rows that no longer exist. They now
branch on model_converter.is_overlay, as the converters do.

Model names carry the test name, since the fixture database is shared across the session.
"""

from types import SimpleNamespace

from lif.mdr_services.datamodel_service import get_datamodel_with_details_by_id
from lif.mdr_services.entity_association_service import get_entity_associations_by_data_model_id
from lif.mdr_services.entity_attribute_association_service import get_entity_attribute_associations_by_data_model_id
from lif.mdr_services.entity_service import get_list_of_entities_for_data_model, get_unique_entity
from lif.mdr_services.attribute_service import get_list_of_attributes_for_data_model, get_unique_attribute
from lif.mdr_services.import_export_service import export_datamodel
from lif.mdr_services.transformation_service import check_transformation_attribute
from lif.mdr_services.valueset_service import (
    get_paginated_value_sets_by_data_model_id,
    get_value_sets_by_data_model_id_and_attributes,
)
from lif.mdr_sql_model.core import (
    Attribute,
    DataModel,
    DataModelType,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
    ValueSet,
)


async def _add(session, row):
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def _install(session, tag) -> SimpleNamespace:
    """An OrgLIF as conversion leaves it: no BaseDataModelId, no inclusion rows, only its own rows."""
    model = await _add(
        session,
        DataModel(
            Name=f"SC_{tag}",
            Type=DataModelType.OrgLIF,
            DataModelVersion="1.0",
            ContributorOrganization="UniconQA",
            Description="",
            Deleted=False,
        ),
    )
    grade = await _add(session, ValueSet(Name="Grade", DataModelId=model.Id))
    course = await _add(session, Entity(Name="Course", UniqueName="Course", DataModelId=model.Id))
    student = await _add(session, Entity(Name="Student", UniqueName="Student", DataModelId=model.Id))
    title = await _add(
        session,
        Attribute(Name="title", UniqueName="Course.title", DataModelId=model.Id, DataType="enum", ValueSetId=grade.Id),
    )
    await _add(session, EntityAttributeAssociation(EntityId=course.Id, AttributeId=title.Id, Name="title", Array=False))
    await _add(
        session, EntityAssociation(ParentEntityId=course.Id, ChildEntityId=student.Id, Name="Students", Array=True)
    )
    return SimpleNamespace(model=model, grade=grade, course=course, student=student, title=title)


async def test_entities_are_the_models_own(test_db_session):
    rows = await _install(test_db_session, "entities")
    _, entities = await get_list_of_entities_for_data_model(test_db_session, rows.model.Id, pagination=False)
    assert {entity.Id for entity in entities} == {rows.course.Id, rows.student.Id}


async def test_attributes_are_the_models_own(test_db_session):
    rows = await _install(test_db_session, "attributes")
    _, attributes = await get_list_of_attributes_for_data_model(test_db_session, rows.model.Id, pagination=False)
    assert [attribute.Id for attribute in attributes] == [rows.title.Id]


async def test_value_sets_are_the_models_own(test_db_session):
    rows = await _install(test_db_session, "value_sets")
    _, value_sets = await get_paginated_value_sets_by_data_model_id(test_db_session, rows.model.Id, pagination=False)
    assert [value_set.Id for value_set in value_sets] == [rows.grade.Id]
    value_sets = await get_value_sets_by_data_model_id_and_attributes(test_db_session, rows.model.Id, [])
    assert [value_set.Id for value_set in value_sets] == [rows.grade.Id]


async def test_associations_are_the_models_own(test_db_session):
    rows = await _install(test_db_session, "associations")
    entity_associations = await get_entity_associations_by_data_model_id(test_db_session, rows.model.Id)
    assert [(a.ParentEntityId, a.ChildEntityId) for a in entity_associations] == [(rows.course.Id, rows.student.Id)]
    _, attribute_associations = await get_entity_attribute_associations_by_data_model_id(
        test_db_session, rows.model.Id, pagination=False
    )
    assert [(a.EntityId, a.AttributeId) for a in attribute_associations] == [(rows.course.Id, rows.title.Id)]


async def test_with_details_lists_the_models_own_rows(test_db_session):
    rows = await _install(test_db_session, "with_details")
    details = await get_datamodel_with_details_by_id(test_db_session, rows.model.Id)
    by_entity = {item.Entity.Id: item for item in details.Entities}
    assert set(by_entity) == {rows.course.Id, rows.student.Id}
    assert [attribute.Id for attribute in by_entity[rows.course.Id].Attributes] == [rows.title.Id]
    assert [child.Id for child in by_entity[rows.course.Id].ChildEntities] == [rows.student.Id]


async def test_legacy_export_has_no_base_model(test_db_session):
    # Exported like any self-contained model: as the base, with no extension.
    rows = await _install(test_db_session, "export")
    exported = await export_datamodel(test_db_session, rows.model.Id)
    assert exported.ExtendedDataModel is None
    assert exported.BaseDataModel.DataModel.Id == rows.model.Id
    assert [entity.Id for entity in exported.BaseDataModel.Entities] == [rows.course.Id, rows.student.Id]


async def test_a_mapping_path_into_it_needs_no_inclusion_rows(test_db_session):
    rows = await _install(test_db_session, "mapping_path")
    await check_transformation_attribute(test_db_session, rows.model, f"{rows.course.Id},-{rows.title.Id}")


async def test_mapping_import_resolves_names_in_the_model_itself(test_db_session):
    # Still given the stored Type: with no base, "the model or its base" is just the model.
    rows = await _install(test_db_session, "unique_names")
    lookup = {"data_model_id": rows.model.Id, "base_data_model_id": None, "data_model_type": DataModelType.OrgLIF}
    assert (await get_unique_entity(test_db_session, unique_name="Course", **lookup)).Id == rows.course.Id
    assert (await get_unique_attribute(test_db_session, unique_name="Course.title", **lookup)).Id == rows.title.Id
