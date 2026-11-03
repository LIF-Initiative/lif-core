"""Postgres-backed tests of the mapping-group converter (issue #1389).

The file rules are tested in test/components/lif/mdr_portability; these cover what needs installed
models: paths resolved against live rows, round trips between installs whose row IDs differ, refusals
read from stored rows, and refused imports writing nothing.

Model names carry the test name, since the fixture database is shared across the session.
"""

import json

import pytest
from sqlmodel import func, select

from lif.mdr_dto.entity_association_dto import CreateEntityAssociationDTO
from lif.mdr_dto.entity_attribute_association_dto import CreateEntityAttributeAssociationDTO
from lif.mdr_portability import PortabilityErrorCode, PortabilityErrorGroup, dump_canonical, parse_mapping_group_file
from lif.mdr_services.association_name import entity_association_name
from lif.mdr_services.entity_association_service import create_entity_association
from lif.mdr_services.entity_attribute_association_service import create_entity_attribute_association
from lif.mdr_services.mapping_group_converter import export_mapping_group, import_mapping_group
from lif.mdr_sql_model.core import (
    Attribute,
    AttributeType,
    DataModel,
    DataModelType,
    ElementType,
    Entity,
    EntityAssociation,
    EntityPlacementType,
    ExpressionLanguageType,
    ExtInclusionsFromBaseDM,
    Transformation,
    TransformationAttribute,
    TransformationGroup,
)

Code = PortabilityErrorCode


async def _install(session, tag, reverse=False):
    """The source and target models, built through the services so association Names are written.

    Source: Person (firstName, lastName) contains Contact (city) and references Organization (name).
    Target: Learner (fullName, city, employer) contains Name (firstName, lastName); Course (title)
    contains Organization twice, as the roles accreditedBy and approvedBy.
    reverse builds every row in the opposite order, so a second install gets different row IDs.
    """
    models = {}
    for side in ("Source", "Target"):
        model = DataModel(
            Name=f"MG{side}_{tag}",
            Type=DataModelType.SourceSchema,
            DataModelVersion="1.0",
            ContributorOrganization="UniconQA",
            Deleted=False,
        )
        session.add(model)
        await session.commit()
        await session.refresh(model)
        models[side] = model

    entity_specs = [
        ("Source", "Person"),
        ("Source", "Contact"),
        ("Source", "Organization"),
        ("Target", "Learner"),
        ("Target", "Name"),
        ("Target", "Course"),
        ("Target", "Organization"),
    ]
    attribute_specs = [
        ("Source", "Person", "firstName"),
        ("Source", "Person", "lastName"),
        ("Source", "Contact", "city"),
        ("Source", "Organization", "name"),
        ("Target", "Learner", "fullName"),
        ("Target", "Learner", "city"),
        ("Target", "Learner", "employer"),
        ("Target", "Name", "firstName"),
        ("Target", "Name", "lastName"),
        ("Target", "Course", "title"),
        ("Target", "Organization", "name"),
    ]
    if reverse:
        entity_specs.reverse()
        attribute_specs.reverse()

    rows = {}
    for side, name in entity_specs:
        entity = Entity(Name=name, UniqueName=name, DataModelId=models[side].Id, Array="No", Required="No")
        session.add(entity)
        await session.commit()
        await session.refresh(entity)
        rows[(side, name)] = entity
    for side, entity_name, name in attribute_specs:
        attribute = Attribute(
            Name=name, UniqueName=f"{entity_name}.{name}", DataModelId=models[side].Id, DataType="xsd:string"
        )
        session.add(attribute)
        await session.commit()
        await session.refresh(attribute)
        rows[(side, entity_name, name)] = attribute
        await create_entity_attribute_association(
            session,
            CreateEntityAttributeAssociationDTO(EntityId=rows[(side, entity_name)].Id, AttributeId=attribute.Id),
        )

    for side, parent, child, relationship, placement in [
        ("Source", "Person", "Contact", None, "Embedded"),
        ("Source", "Person", "Organization", "employer", "Reference"),
        ("Target", "Learner", "Name", None, "Embedded"),
        ("Target", "Course", "Organization", "accreditedBy", "Embedded"),
    ]:
        await create_entity_association(
            session,
            CreateEntityAssociationDTO(
                ParentEntityId=rows[(side, parent)].Id,
                ChildEntityId=rows[(side, child)].Id,
                Relationship=relationship,
                Placement=placement,
            ),
        )
    # The service refuses a second association between one parent and child, but the seed has such
    # roles (ADR metadata_repository/0010 counts 8 in model 1), so the second role is written directly.
    session.add(
        EntityAssociation(
            ParentEntityId=rows[("Target", "Course")].Id,
            ChildEntityId=rows[("Target", "Organization")].Id,
            Relationship="approvedBy",
            Placement=EntityPlacementType.Embedded,
            Name=entity_association_name("approvedBy", "Embedded", "Organization"),
            Array=False,
        )
    )
    await session.commit()
    return models, rows


def _file(tag, mappings) -> bytes:
    """A file in canonical form, so an export of it must match it byte for byte."""
    content = {
        "Format": {"Type": "lif-mdr-mapping-group", "Version": 1},
        "Details": {
            "Source": {"Name": f"MGSource_{tag}", "Version": "1.0", "ContributorOrganization": "UniconQA"},
            "Target": {"Name": f"MGTarget_{tag}", "Version": "1.0", "ContributorOrganization": "UniconQA"},
            "Version": "1.0",
            "Name": "Person to Learner",
            "Notes": "hand-written fixture",
        },
        "Mappings": mappings,
    }
    return dump_canonical(parse_mapping_group_file(json.dumps(content).encode()))


def _mapping(target, sources, expression, **extra):
    return {
        "Target": {"Path": target},
        "Sources": [{"Path": source} for source in sources],
        "ExpressionLanguage": "JSONata",
        "Expression": expression,
        "Name": target,
        **extra,
    }


MAPPINGS = [
    # One source to one target, into a nested entity.
    _mapping("Learner,Name,firstName", ["Person,firstName"], "Person.firstName"),
    # One source to many targets: lastName feeds this and fullName.
    _mapping("Learner,Name,lastName", ["Person,lastName"], "Person.lastName"),
    # Many sources to one target, with the per-mapping fields a file carries.
    {
        **_mapping(
            "Learner,fullName", ["Person,firstName", "Person,lastName"], "Person.firstName & ' ' & Person.lastName"
        ),
        "Description": "first and last name",
        "ActivationDate": "2026-01-01T00:00:00Z",
        "Sources": [{"Path": "Person,firstName", "Notes": "given name"}, {"Path": "Person,lastName"}],
    },
    # Through a nested source entity, and through a reference.
    _mapping("Learner,city", ["Person,Contact,city"], "Person.Contact.city"),
    _mapping("Learner,employer", ["Person,employerRefOrganization,name"], "Person.employerRefOrganization.name"),
]


def _codes(error: PortabilityErrorGroup) -> list:
    return sorted(e.code for e in error.exceptions)


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_a_group_round_trips_between_installs_byte_for_byte(test_db_session):
    session, tag = test_db_session, "roundtrip"
    file_a = _file(tag, MAPPINGS)

    models_1, _ = await _install(session, tag)
    group_1 = await import_mapping_group(session, parse_mapping_group_file(file_a))
    await session.commit()
    file_b = dump_canonical(await export_mapping_group(session, group_1))
    assert file_b == file_a

    # A second install: the same models by identity, built in reverse so every row ID differs.
    for model in models_1.values():
        model.Deleted = True
    await session.commit()
    _, rows_2 = await _install(session, tag, reverse=True)
    group_2 = await import_mapping_group(session, parse_mapping_group_file(file_b))
    await session.commit()
    file_c = dump_canonical(await export_mapping_group(session, group_2))
    assert file_c == file_a

    stored = (
        await session.execute(
            select(TransformationAttribute.EntityIdPath)
            .join(Transformation, Transformation.Id == TransformationAttribute.TransformationId)
            .where(Transformation.TransformationGroupId == group_2, Transformation.Name == "Learner,employer")
            .where(TransformationAttribute.AttributeType == AttributeType.Source)
        )
    ).scalar_one()
    person, organization = rows_2[("Source", "Person")].Id, rows_2[("Source", "Organization")].Id
    assert stored == f"{person},{organization},-{rows_2[('Source', 'Organization', 'name')].Id}"


async def test_an_imported_group_is_not_active(test_db_session):
    session, tag = test_db_session, "inactive"
    await _install(session, tag)
    group_id = await import_mapping_group(session, parse_mapping_group_file(_file(tag, MAPPINGS[:1])))
    await session.commit()
    group = await session.get(TransformationGroup, group_id)
    assert (group.ActivationDate, group.DeprecationDate) == (None, None)


@pytest.mark.parametrize(
    "tag, mappings, codes",
    [
        # Two roles store the same EntityIdPath, so a role path is refused until they can be told apart.
        ("role", [_mapping("Course,accreditedByOrganization,name", ["Person,firstName"], "x")], [Code.PATH_INVALID]),
        # A path the model does not have.
        ("unknown", [_mapping("Learner,nickname", ["Person,firstName"], "x")], [Code.PATH_INVALID]),
        # One good mapping does not get written when another is refused (a path ending at an entity).
        (
            "partial",
            [
                _mapping("Learner,city", ["Person,Contact,city"], "x"),
                _mapping("Learner,Name", ["Person,lastName"], "x"),
            ],
            [Code.PATH_INVALID],
        ),
    ],
)
async def test_a_refused_import_writes_nothing(test_db_session, tag, mappings, codes):
    session, tag = test_db_session, f"refused_{tag}"
    await _install(session, tag)
    before = [await _count(session, model) for model in (TransformationGroup, Transformation, TransformationAttribute)]

    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_mapping_group(session, parse_mapping_group_file(_file(tag, mappings)))
    await session.rollback()

    assert _codes(exc_info.value) == codes
    after = [await _count(session, model) for model in (TransformationGroup, Transformation, TransformationAttribute)]
    assert after == before


async def test_import_refuses_missing_models_and_an_existing_version(test_db_session):
    session, tag = test_db_session, "exists"
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_mapping_group(session, parse_mapping_group_file(_file(tag, MAPPINGS[:1])))
    assert _codes(exc_info.value) == [Code.MODEL_MISSING, Code.MODEL_MISSING]
    await session.rollback()

    await _install(session, tag)
    file = parse_mapping_group_file(_file(tag, MAPPINGS[:1]))
    await import_mapping_group(session, file)
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await import_mapping_group(session, file)
    assert _codes(exc_info.value) == [Code.GROUP_EXISTS]


async def _imported(session, tag, mappings=MAPPINGS):
    models, rows = await _install(session, tag)
    group_id = await import_mapping_group(session, parse_mapping_group_file(_file(tag, mappings)))
    await session.commit()
    transformations = {
        t.Name: t
        for t in (
            await session.execute(select(Transformation).where(Transformation.TransformationGroupId == group_id))
        ).scalars()
    }
    return models, rows, group_id, transformations


async def _target_row(session, transformation_id):
    return (
        await session.execute(
            select(TransformationAttribute).where(
                TransformationAttribute.TransformationId == transformation_id,
                TransformationAttribute.AttributeType == AttributeType.Target,
            )
        )
    ).scalar_one()


async def test_export_refuses_a_rule_that_is_not_jsonata(test_db_session):
    session = test_db_session
    _, _, group_id, transformations = await _imported(session, "pseudo")
    transformations["Learner,city"].ExpressionLanguage = ExpressionLanguageType.LIF_Pseudo_Code
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_mapping_group(session, group_id)
    assert _codes(exc_info.value) == [Code.EXPRESSION_LANGUAGE_NOT_PORTABLE]
    assert exc_info.value.exceptions[0].element == "Mappings[Learner,city]"


async def test_export_refuses_a_transformation_with_no_target_or_two(test_db_session):
    session = test_db_session
    _, rows, group_id, transformations = await _imported(session, "targets")
    (await _target_row(session, transformations["Learner,city"].Id)).Deleted = True
    employer = transformations["Learner,employer"]
    learner, full_name = rows[("Target", "Learner")], rows[("Target", "Learner", "fullName")]
    session.add(
        TransformationAttribute(
            TransformationId=employer.Id,
            EntityId=learner.Id,
            AttributeId=full_name.Id,
            AttributeType=AttributeType.Target,
            EntityIdPath=f"{learner.Id},-{full_name.Id}",
        )
    )
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_mapping_group(session, group_id)
    assert _codes(exc_info.value) == [Code.MAPPING_TARGET_MISSING, Code.MAPPING_TARGET_MULTIPLE]


async def test_export_refuses_two_transformations_writing_one_target(test_db_session):
    session = test_db_session
    _, _, group_id, transformations = await _imported(session, "shared")
    city_target = await _target_row(session, transformations["Learner,city"].Id)
    employer_target = await _target_row(session, transformations["Learner,employer"].Id)
    employer_target.AttributeId, employer_target.EntityIdPath = city_target.AttributeId, city_target.EntityIdPath
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_mapping_group(session, group_id)
    assert _codes(exc_info.value) == [Code.MAPPING_TARGET_SHARED]


async def test_export_refuses_a_stored_role_path(test_db_session):
    session = test_db_session
    _, rows, group_id, transformations = await _imported(session, "role")
    target = await _target_row(session, transformations["Learner,city"].Id)
    course, organization = rows[("Target", "Course")], rows[("Target", "Organization")]
    name = rows[("Target", "Organization", "name")]
    target.EntityId, target.AttributeId = organization.Id, name.Id
    target.EntityIdPath = f"{course.Id},{organization.Id},-{name.Id}"
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_mapping_group(session, group_id)
    assert _codes(exc_info.value) == [Code.PATH_INVALID]
    assert "'accreditedByOrganization', 'approvedByOrganization'" in exc_info.value.exceptions[0].reason


async def test_export_refuses_an_overlay_model(test_db_session):
    session = test_db_session
    models, rows, group_id, _ = await _imported(session, "overlay")
    session.add(
        ExtInclusionsFromBaseDM(
            ExtDataModelId=models["Target"].Id,
            ElementType=ElementType.Entity,
            IncludedElementId=rows[("Target", "Learner")].Id,
        )
    )
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_mapping_group(session, group_id)
    assert _codes(exc_info.value) == [Code.NOT_MIGRATED]


async def test_export_refuses_an_overlay_model_found_by_its_base(test_db_session):
    # An overlay built on a base model but with no inclusion rows, as model 28 is on demo.
    session = test_db_session
    models, _, group_id, _ = await _imported(session, "overlay_base")
    models["Target"].BaseDataModelId = models["Source"].Id
    session.add(models["Target"])
    await session.commit()
    with pytest.raises(PortabilityErrorGroup) as exc_info:
        await export_mapping_group(session, group_id)
    assert _codes(exc_info.value) == [Code.NOT_MIGRATED]
