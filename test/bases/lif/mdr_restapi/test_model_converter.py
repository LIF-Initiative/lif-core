"""Postgres-backed tests of the model converter (issue #1333).

The file rules are tested in test/components/lif/mdr_portability; these cover what needs stored rows:
how each stored value is written to the file, which associations belong to a model, the constructs
export refuses as not yet migrated (Portability Spec §11), what import stores, round trips between
installs whose row IDs differ, and refused imports writing nothing.

Model names carry the test name, since the fixture database is shared across the session.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import func, select

from lif.mdr_portability import PortabilityErrorCode, PortabilityErrorGroup, dump_canonical, parse_model_file
from lif.mdr_services.model_converter import export_model, import_model
from lif.mdr_sql_model.core import (
    AccessType,
    Attribute,
    Constraint,
    ConstraintType,
    DataModel,
    DataModelConstraints,
    DataModelType,
    DatamodelElementType,
    ElementType,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
    EntityPlacementType,
    ExtInclusionsFromBaseDM,
    ValueSet,
    ValueSetValue,
)

Code = PortabilityErrorCode
JANUARY = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _add(session, row):
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def _install(session, tag):
    """A model with every kind of stored value export translates, and a second model beside it.

    Course references Organization as AccreditedBy and contains it as ApprovedBy, and contains a list
    of Students. A soft-deleted entity, and the association to it, count as absent.
    """
    model = await _add(
        session,
        DataModel(
            Name=f"MC_{tag}",
            Type=DataModelType.SourceSchema,
            DataModelVersion="1.0",
            ContributorOrganization="UniconQA",
            CopiedFromName="LIF",
            CopiedFromVersion="2.0",
            CopiedFromContributorOrganization="LIF",
            Description="",
            Deleted=False,
        ),
    )
    other = await _add(
        session,
        DataModel(
            Name=f"MCOther_{tag}",
            Type=DataModelType.SourceSchema,
            DataModelVersion="1.0",
            ContributorOrganization="UniconQA",
            Deleted=False,
        ),
    )
    rows = {"model": model, "other": other}
    grade = rows["Grade"] = await _add(session, ValueSet(Name="Grade", DataModelId=model.Id))
    for value_name, value in (("A", "4"), ("B", "3")):
        rows[f"Grade.{value_name}"] = await _add(
            session, ValueSetValue(ValueSetId=grade.Id, DataModelId=model.Id, ValueName=value_name, Value=value)
        )
    rows["Unused"] = await _add(session, ValueSet(Name="Unused", DataModelId=model.Id))
    rows["OtherSet"] = await _add(session, ValueSet(Name="OtherSet", DataModelId=other.Id))

    for name, extra in [
        ("Course", {"Required": "Yes", "LevelOfAccess": AccessType.Restricted, "Queryable": True}),
        ("Organization", {"Required": "No", "ActivationDate": JANUARY}),
        ("Student", {"Modifiable": True}),
        ("Removed", {"Deleted": True}),
    ]:
        rows[name] = await _add(session, Entity(Name=name, UniqueName=name, DataModelId=model.Id, **extra))
    rows["Other"] = await _add(session, Entity(Name="Other", UniqueName="Other", DataModelId=other.Id))

    for entity, name, extra in [
        ("Course", "title", {"DataType": "string", "Required": "Yes"}),
        ("Student", "grade", {"DataType": "enum", "ValueSetId": grade.Id}),
        ("Organization", "name", {"DataType": "string", "Example": "Acme"}),
    ]:
        attribute = await _add(
            session, Attribute(Name=name, UniqueName=f"{entity}.{name}", DataModelId=model.Id, **extra)
        )
        rows[f"{entity}.{name}"] = attribute
        await _add(
            session,
            EntityAttributeAssociation(EntityId=rows[entity].Id, AttributeId=attribute.Id, Name=name, Array=False),
        )
    rows["Other.thing"] = await _add(
        session, Attribute(Name="thing", UniqueName="Other.thing", DataModelId=other.Id, DataType="string")
    )

    for parent, child, name, extra in [
        ("Course", "Organization", "AccreditedBy", {"Placement": EntityPlacementType.Reference, "Array": False}),
        ("Course", "Organization", "ApprovedBy", {"Placement": EntityPlacementType.Embedded, "Array": False}),
        ("Course", "Student", "Students", {"Array": True}),
        ("Course", "Removed", "Removed", {"Array": False}),
    ]:
        rows[f"{parent}.{name}"] = await _add(
            session, EntityAssociation(ParentEntityId=rows[parent].Id, ChildEntityId=rows[child].Id, Name=name, **extra)
        )
    return rows


def _expected_file(tag) -> bytes:
    content = {
        "Format": {"Type": "lif-mdr-model", "Version": 1},
        "Details": {
            "Name": f"MC_{tag}",
            "Version": "1.0",
            "ContributorOrganization": "UniconQA",
            "CopiedFrom": {"Name": "LIF", "Version": "2.0", "ContributorOrganization": "LIF"},
            "Description": "",
        },
        "ValueSets": [
            {"Name": "Grade", "Values": [{"ValueName": "A", "Value": "4"}, {"ValueName": "B", "Value": "3"}]},
            {"Name": "Unused", "Values": []},
        ],
        "Entities": [
            {
                "UniqueName": "Course",
                "Name": "Course",
                "LevelOfAccess": "Restricted",
                "Queryable": True,
                "Modifiable": False,
                "Required": True,
            },
            {
                "UniqueName": "Organization",
                "Name": "Organization",
                "LevelOfAccess": "Public",
                "Queryable": False,
                "Modifiable": False,
                "ActivationDate": "2026-01-01T00:00:00Z",
            },
            {
                "UniqueName": "Student",
                "Name": "Student",
                "LevelOfAccess": "Public",
                "Queryable": False,
                "Modifiable": True,
            },
        ],
        "Attributes": [
            {
                "UniqueName": "Course.title",
                "Name": "title",
                "DataType": "string",
                "LevelOfAccess": "Public",
                "Queryable": False,
                "Modifiable": False,
                "Required": True,
            },
            {
                "UniqueName": "Student.grade",
                "Name": "grade",
                "DataType": "enum",
                "ValueSet": {"ValueSet": "Grade"},
                "LevelOfAccess": "Public",
                "Queryable": False,
                "Modifiable": False,
            },
            {
                "UniqueName": "Organization.name",
                "Name": "name",
                "DataType": "string",
                "LevelOfAccess": "Public",
                "Queryable": False,
                "Modifiable": False,
                "Example": "Acme",
            },
        ],
        "Associations": [
            {
                "Parent": {"Entity": "Course"},
                "Child": {"Entity": "Organization"},
                "Name": "AccreditedBy",
                "Reference": True,
            },
            {"Parent": {"Entity": "Course"}, "Child": {"Entity": "Organization"}, "Name": "ApprovedBy"},
            {"Parent": {"Entity": "Course"}, "Child": {"Entity": "Student"}, "Name": "Students", "Array": True},
            {"Parent": {"Entity": "Course"}, "Child": {"Attribute": "Course.title"}, "Name": "title"},
            {"Parent": {"Entity": "Student"}, "Child": {"Attribute": "Student.grade"}, "Name": "grade"},
            {"Parent": {"Entity": "Organization"}, "Child": {"Attribute": "Organization.name"}, "Name": "name"},
        ],
    }
    return dump_canonical(parse_model_file(json.dumps(content).encode()))


async def _collect_refusals(session, data_model_id) -> list[tuple[PortabilityErrorCode, str]]:
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_model(session, data_model_id)
    return [(error.code, error.element) for error in exc_info.value.exceptions]


async def test_export_writes_each_stored_value_as_the_file_defines_it(test_db_session):
    session, tag = test_db_session, "export"
    rows = await _install(session, tag)
    assert dump_canonical(await export_model(session, rows["model"].Id)) == _expected_file(tag)


async def test_export_leaves_out_associations_another_model_declared_on_an_end_it_owns(test_db_session):
    # As an overlay's additions to its base model's entities are the overlay's content (§11).
    session, tag = test_db_session, "declared_by_other"
    rows = await _install(session, tag)
    await _add(
        session,
        EntityAttributeAssociation(
            EntityId=rows["Course"].Id,
            AttributeId=rows["Other.thing"].Id,
            Array=False,
            Name="thing",
            ExtendedByDataModelId=rows["other"].Id,
        ),
    )
    assert dump_canonical(await export_model(session, rows["model"].Id)) == _expected_file(tag)


async def _set(session, row, **fields):
    for field, value in fields.items():
        setattr(row, field, value)
    await _add(session, row)


async def _add_extension(session, rows):
    await _set(session, rows["Course"], Extension=True)
    return [(Code.NOT_MIGRATED, "Entities[Course]")]


async def _add_entity_typed_attribute(session, rows):
    await _set(session, rows["Course.title"], DataType="entity")
    return [(Code.NOT_MIGRATED, "Attributes[Course.title]")]


async def _remove_data_type(session, rows):
    await _set(session, rows["Course.title"], DataType=None)
    return [(Code.NOT_MIGRATED, "Attributes[Course.title]")]


async def _use_another_models_value_set(session, rows):
    await _set(session, rows["Student.grade"], ValueSetId=rows["OtherSet"].Id)
    return [(Code.NOT_MIGRATED, "Attributes[Student.grade].ValueSet")]


async def _add_unassociated_attribute(session, rows):
    model_id = rows["model"].Id
    await _add(session, Attribute(Name="loose", UniqueName="Course.loose", DataModelId=model_id, DataType="string"))
    return [(Code.NOT_MIGRATED, "Attributes[Course.loose]")]


async def _add_cross_model_child(session, rows):
    await _add(
        session,
        EntityAssociation(ParentEntityId=rows["Course"].Id, ChildEntityId=rows["Other"].Id, Name="Other", Array=False),
    )
    return [(Code.NOT_MIGRATED, "Associations[Course, Other]")]


async def _declare_an_association_by_extension(session, rows):
    await _set(session, rows["Course.Students"], ExtendedByDataModelId=rows["model"].Id)
    return [(Code.NOT_MIGRATED, "Associations[Course, Students]")]


async def _declare_an_association_by_a_model_owning_neither_end(session, rows):
    # It belongs to the model both ends are in (§11), but is stored the old way.
    await _set(session, rows["Course.Students"], ExtendedByDataModelId=rows["other"].Id)
    return [(Code.NOT_MIGRATED, "Associations[Course, Students]")]


async def _add_constraint(session, rows):
    await _add(
        session, Constraint(Name="max", ConstraintType=ConstraintType.MaxValue, AttributeId=rows["Course.title"].Id)
    )
    return [(Code.NOT_MIGRATED, "Details")]


async def _add_value_extension_notes(session, rows):
    # ExtensionNotes alone counts, without the Extension flag.
    await _set(session, rows["Grade.A"], ExtensionNotes="local")
    return [(Code.NOT_MIGRATED, "ValueSets[Grade].Values[A]")]


async def _add_association_extension(session, rows):
    await _set(session, rows["Course.Students"], Extension=True)
    return [(Code.NOT_MIGRATED, "Associations[Course, Students]")]


async def _remove_association_name(session, rows):
    await _set(session, rows["Course.Students"], Name=None)
    return [(Code.NOT_MIGRATED, "Associations[Course, ]")]


async def _add_target_entity(session, rows):
    # TargetEntityId marks an entity-typed attribute even when DataType does not say entity.
    await _set(session, rows["Course.title"], TargetEntityId=rows["Student"].Id)
    return [(Code.NOT_MIGRATED, "Attributes[Course.title]")]


async def _add_model_constraint(session, rows):
    await _add(
        session,
        DataModelConstraints(
            ForDataModelId=rows["model"].Id,
            ElementType=DatamodelElementType.Entity,
            ElementId=rows["Course"].Id,
            Contributor="UniconQA",
            ContributorOrganization="UniconQA",
        ),
    )
    return [(Code.NOT_MIGRATED, "Details")]


@pytest.mark.parametrize(
    "make_not_migrated",
    [
        _add_extension,
        _add_value_extension_notes,
        _add_association_extension,
        _remove_association_name,
        _add_target_entity,
        _add_model_constraint,
        _add_entity_typed_attribute,
        _remove_data_type,
        _use_another_models_value_set,
        _add_unassociated_attribute,
        _add_cross_model_child,
        _declare_an_association_by_extension,
        _declare_an_association_by_a_model_owning_neither_end,
        _add_constraint,
    ],
)
async def test_export_refuses_each_construct_that_is_not_migrated(test_db_session, make_not_migrated):
    session, tag = test_db_session, make_not_migrated.__name__
    rows = await _install(session, tag)
    expected = await make_not_migrated(session, rows)
    assert await _collect_refusals(session, rows["model"].Id) == expected


async def test_export_refuses_an_overlay_on_that_alone(test_db_session):
    session, tag = test_db_session, "overlay"
    rows = await _install(session, tag)
    await _set(session, rows["model"], BaseDataModelId=rows["other"].Id)
    await _set(session, rows["Course"], Extension=True)
    assert await _collect_refusals(session, rows["model"].Id) == [(Code.NOT_MIGRATED, "Details")]


async def test_export_refuses_an_overlay_found_by_its_inclusion_rows(test_db_session):
    session, tag = test_db_session, "overlay_inclusions"
    rows = await _install(session, tag)
    await _add(
        session,
        ExtInclusionsFromBaseDM(
            ExtDataModelId=rows["model"].Id, ElementType=ElementType.Entity, IncludedElementId=rows["Other"].Id
        ),
    )
    assert await _collect_refusals(session, rows["model"].Id) == [(Code.NOT_MIGRATED, "Details")]


async def test_export_leaves_out_associations_the_model_does_not_own(test_db_session):
    # An undeclared association is its parent's model's, here the other model's. One declared by a model
    # that owns neither end, with ends in two models, belongs to no model (§11).
    session, tag = test_db_session, "not_owned"
    rows = await _install(session, tag)
    third = await _add(
        session,
        DataModel(
            Name=f"MCThird_{tag}",
            Type=DataModelType.SourceSchema,
            DataModelVersion="1.0",
            ContributorOrganization="UniconQA",
            Deleted=False,
        ),
    )
    await _add(
        session,
        EntityAssociation(
            ParentEntityId=rows["Other"].Id, ChildEntityId=rows["Student"].Id, Name="Student", Array=False
        ),
    )
    await _add(
        session,
        EntityAttributeAssociation(
            EntityId=rows["Course"].Id,
            AttributeId=rows["Other.thing"].Id,
            Name="thing",
            Array=False,
            ExtendedByDataModelId=third.Id,
        ),
    )
    assert dump_canonical(await export_model(session, rows["model"].Id)) == _expected_file(tag)


async def test_export_refuses_a_partial_copied_from(test_db_session):
    session, tag = test_db_session, "partial_copied_from"
    rows = await _install(session, tag)
    await _set(session, rows["model"], CopiedFromVersion=None)
    assert await _collect_refusals(session, rows["model"].Id) == [
        (Code.MODEL_IDENTITY_INCOMPLETE, "Details.CopiedFrom.Version")
    ]


async def test_export_refuses_a_stored_value_the_format_does_not_allow_by_name(test_db_session):
    session, tag = test_db_session, "blank_name"
    rows = await _install(session, tag)
    await _set(session, rows["Course"], Name=" ")
    assert await _collect_refusals(session, rows["model"].Id) == [(Code.FIELD_INVALID, "Entities[Course].Name")]


async def test_export_refuses_a_model_that_is_not_installed(test_db_session):
    session, tag = test_db_session, "missing"
    rows = await _install(session, tag)
    await _set(session, rows["model"], Deleted=True)
    assert await _collect_refusals(session, rows["model"].Id) == [(Code.MODEL_MISSING, "Details")]


async def test_every_seed_model_exports_or_is_refused_by_name(seed_db_session):
    # The seed's models are not yet migrated (§11), so most are refused. None may fail any other way.
    allowed = {Code.NOT_MIGRATED, Code.MODEL_IDENTITY_INCOMPLETE}
    for model in (await seed_db_session.execute(select(DataModel).where(DataModel.Deleted.is_not(True)))).scalars():
        try:
            await export_model(seed_db_session, model.Id)
        except PortabilityErrorGroup as group:
            assert {error.code for error in group.exceptions} <= allowed, model.Name


REFERENCE_MODEL = (
    Path(__file__).parents[3] / "components/lif/mdr_portability/fixtures/test_reference_target_model_file.json"
)


def _model_file(tag, mutate=None) -> bytes:
    """The reference target model, named for the test, in canonical form.

    It covers what #1333 asks a round trip to: a copy with CopiedFrom, non-default flags, Required and
    Array, references including a recursive one, two roles under one parent, a shared entity, value sets
    no attribute uses and values whose Value differs from their ValueName, and an entity and an
    attribute sharing a UniqueName.
    """
    content = json.loads(REFERENCE_MODEL.read_text())
    content["Details"]["Name"] = f"RT_{tag}"
    if mutate:
        mutate(content)
    return dump_canonical(parse_model_file(json.dumps(content).encode()))


def _count_id_keys(node) -> int:
    if isinstance(node, dict):
        return sum((key == "Id" or key.endswith("Id")) + _count_id_keys(value) for key, value in node.items())
    if isinstance(node, list):
        return sum(_count_id_keys(item) for item in node)
    return 0


async def test_a_model_round_trips_between_installs_byte_for_byte(test_db_session):
    session, tag = test_db_session, "roundtrip"
    file_a = _model_file(tag)

    model_1 = await import_model(session, parse_model_file(file_a))
    await session.commit()
    file_b = dump_canonical(await export_model(session, model_1))
    assert file_b == file_a

    # A second install: the first is retired, and the same model imported again gets new row IDs.
    await _set(session, await session.get(DataModel, model_1), Deleted=True)
    model_2 = await import_model(session, parse_model_file(file_b))
    await session.commit()
    file_c = dump_canonical(await export_model(session, model_2))
    assert file_c == file_a

    assert model_2 != model_1
    first_ids = set((await session.execute(select(Entity.Id).where(Entity.DataModelId == model_1))).scalars())
    second_ids = set((await session.execute(select(Entity.Id).where(Entity.DataModelId == model_2))).scalars())
    assert first_ids and second_ids and not first_ids & second_ids
    assert _count_id_keys(json.loads(file_c)) == 0


async def test_import_stores_what_the_schema_generator_reads(test_db_session):
    # Until the generator reads the new columns (#1395), an element's Array is true when any
    # association places it as a list, and Required and Array are stored as Yes or No.
    session, tag = test_db_session, "stored"
    model_id = await import_model(session, parse_model_file(_model_file(tag)))
    await session.commit()

    model = await session.get(DataModel, model_id)
    assert (model.Type, model.CopiedFromName, model.State) == (DataModelType.SourceSchema, "State LIF", "Draft")
    entities = {
        entity.UniqueName: entity
        for entity in (await session.execute(select(Entity).where(Entity.DataModelId == model_id))).scalars()
    }
    assert (entities["Person.Contact"].Required, entities["Person.Contact"].Array) == ("Yes", "Yes")
    assert (entities["Organization"].Required, entities["Organization"].Array) == ("No", "No")
    # A list under Person, single under Organization: stored as a list.
    assert entities["Identifier"].Array == "Yes"
    assert entities["Person.Contact"].LevelOfAccess == AccessType.Restricted
    assert entities["Person.Contact"].Modifiable

    entity_ids = [entity.Id for entity in entities.values()]
    associations = {
        (row.ParentEntityId, row.Name): row
        for row in (
            await session.execute(select(EntityAssociation).where(EntityAssociation.ParentEntityId.in_(entity_ids)))
        ).scalars()
    }
    accredited_by = associations[(entities["Course"].Id, "AccreditedBy")]
    contact = associations[(entities["Person"].Id, "Contact")]
    assert (accredited_by.Placement, accredited_by.Relationship) == (EntityPlacementType.Reference, None)
    assert (contact.Placement, contact.Array) == (EntityPlacementType.Embedded, True)


async def _count_rows(session, model_class) -> int:
    return (await session.execute(select(func.count()).select_from(model_class))).scalar_one()


def _add_cycle(content):
    content["Associations"].append(
        {"Parent": {"Entity": "Person.Contact"}, "Child": {"Entity": "Person"}, "Name": "Owner"}
    )


def _reference_an_attribute(content):
    for association in content["Associations"]:
        if association["Child"] == {"Attribute": "Person.ssn"}:
            association["Reference"] = True


def _use_a_missing_value_set(content):
    for attribute in content["Attributes"]:
        if attribute["UniqueName"] == "Person.lunchStatus":
            attribute["ValueSet"] = {"ValueSet": "Missing"}


@pytest.mark.parametrize(
    "mutate, code",
    [
        (_add_cycle, Code.ASSOCIATION_CYCLE),
        (_reference_an_attribute, Code.REFERENCE_INVALID),
        (_use_a_missing_value_set, Code.ELEMENT_REFERENCE_UNRESOLVED),
    ],
)
async def test_a_refused_import_writes_nothing(test_db_session, mutate, code):
    session, tag = test_db_session, f"refused_{mutate.__name__}"
    tables = (DataModel, Entity, Attribute, ValueSet, EntityAssociation, EntityAttributeAssociation)
    counts = [await _count_rows(session, model_class) for model_class in tables]
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_model(session, parse_model_file(_model_file(tag, mutate)))
    await session.commit()
    assert {error.code for error in exc_info.value.exceptions} == {code}
    assert [await _count_rows(session, model_class) for model_class in tables] == counts


async def test_import_refuses_a_model_that_is_already_installed(test_db_session):
    session, tag = test_db_session, "exists"
    file = parse_model_file(_model_file(tag))
    await import_model(session, file)
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_model(session, file)
    assert [(error.code, error.element) for error in exc_info.value.exceptions] == [(Code.MODEL_EXISTS, "Details")]
    live = (
        select(func.count()).select_from(DataModel).where(DataModel.Name == f"RT_{tag}", DataModel.Deleted.is_not(True))
    )
    assert (await session.execute(live)).scalar_one() == 1


async def test_import_reports_every_refusal_at_once(test_db_session):
    session, tag = test_db_session, "every_refusal"
    await import_model(session, parse_model_file(_model_file(tag)))
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_model(session, parse_model_file(_model_file(tag, _add_cycle)))
    assert {error.code for error in exc_info.value.exceptions} == {Code.ASSOCIATION_CYCLE, Code.MODEL_EXISTS}


async def test_import_leaves_the_commit_to_the_caller(test_db_session):
    # A single transaction (§8): a caller that rolls back keeps nothing of the import.
    session, tag = test_db_session, "rolled_back"
    await import_model(session, parse_model_file(_model_file(tag)))
    await session.rollback()
    named = select(func.count()).select_from(DataModel).where(DataModel.Name == f"RT_{tag}")
    assert (await session.execute(named)).scalar_one() == 0


def _place_an_attribute_in_a_list(content):
    for association in content["Associations"]:
        if association["Child"] == {"Attribute": "Person.lunchStatus"}:
            association["Array"] = True


async def test_an_attribute_placed_as_a_list_is_stored_as_one_and_round_trips(test_db_session):
    session, tag = test_db_session, "attribute_list"
    file = _model_file(tag, _place_an_attribute_in_a_list)
    model_id = await import_model(session, parse_model_file(file))
    await session.commit()
    attribute = (
        await session.execute(
            select(Attribute).where(Attribute.DataModelId == model_id, Attribute.UniqueName == "Person.lunchStatus")
        )
    ).scalar_one()
    association = (
        await session.execute(
            select(EntityAttributeAssociation).where(EntityAttributeAssociation.AttributeId == attribute.Id)
        )
    ).scalar_one()
    assert (attribute.Array, association.Array) == ("Yes", True)
    assert dump_canonical(await export_model(session, model_id)) == file


def _set_version(version):
    def mutate(content):
        content["Details"]["Version"] = version

    return mutate


async def test_another_version_of_an_installed_model_imports(test_db_session):
    # MODEL_EXISTS compares the whole identity: Name, Version and ContributorOrganization.
    session, tag = test_db_session, "new_version"
    await import_model(session, parse_model_file(_model_file(tag)))
    await import_model(session, parse_model_file(_model_file(tag, _set_version("2.0"))))
    await session.commit()
    live = (
        select(func.count()).select_from(DataModel).where(DataModel.Name == f"RT_{tag}", DataModel.Deleted.is_not(True))
    )
    assert (await session.execute(live)).scalar_one() == 2
