"""Postgres-backed tests of the by-value-set value-mapping lookup (issue #1440).

The pair is read from the values' own ValueSetId, not from the mapping's SourceValueSetId and
TargetValueSetId, which are NULL or disagree with the values on most of the seed's rows (spec §11).

Model names carry the test name, since the fixture database is shared across the session.
"""

from lif.mdr_services.value_mapping_service import get_value_mappings_by_value_set_ids
from lif.mdr_sql_model.core import DataModel, DataModelType, ValueSet, ValueSetValue, ValueSetValueMapping


async def _value_set(session, name):
    """A model with one value set holding one value. Returns (value set, value)."""
    model = DataModel(
        Name=name,
        Type=DataModelType.SourceSchema,
        DataModelVersion="1.0",
        ContributorOrganization="UniconQA",
        Deleted=False,
    )
    session.add(model)
    await session.flush()
    value_set = ValueSet(Name=name, DataModelId=model.Id, Deleted=False)
    session.add(value_set)
    await session.flush()
    value = ValueSetValue(ValueSetId=value_set.Id, DataModelId=model.Id, Value="A", ValueName="A", Deleted=False)
    session.add(value)
    await session.flush()
    return value_set, value


async def _ids(session, **kwargs):
    return [m.Id for m in await get_value_mappings_by_value_set_ids(session, **kwargs)]


async def test_a_mapping_with_no_value_set_columns_is_found_by_its_values_value_sets(test_db_session):
    source_set, source_value = await _value_set(test_db_session, "VMNull_Source")
    target_set, target_value = await _value_set(test_db_session, "VMNull_Target")
    mapping = ValueSetValueMapping(SourceValueId=source_value.Id, TargetValueId=target_value.Id, Deleted=False)
    test_db_session.add(mapping)
    await test_db_session.commit()

    assert await _ids(test_db_session, source_value_set_id=source_set.Id, target_value_set_id=target_set.Id) == [
        mapping.Id
    ]
    assert await _ids(test_db_session, source_value_set_id=source_set.Id) == [mapping.Id]
    assert await _ids(test_db_session, target_value_set_id=target_set.Id) == [mapping.Id]


async def test_a_mapping_whose_value_set_columns_disagree_is_found_only_under_its_values(test_db_session):
    source_set, source_value = await _value_set(test_db_session, "VMWrong_Source")
    target_set, target_value = await _value_set(test_db_session, "VMWrong_Target")
    other_set, _ = await _value_set(test_db_session, "VMWrong_Other")
    mapping = ValueSetValueMapping(
        SourceValueId=source_value.Id,
        TargetValueId=target_value.Id,
        SourceValueSetId=other_set.Id,
        TargetValueSetId=other_set.Id,
        Deleted=False,
    )
    test_db_session.add(mapping)
    await test_db_session.commit()

    assert await _ids(test_db_session, source_value_set_id=source_set.Id, target_value_set_id=target_set.Id) == [
        mapping.Id
    ]
    assert await _ids(test_db_session, source_value_set_id=other_set.Id) == []
    assert await _ids(test_db_session, target_value_set_id=other_set.Id) == []


async def test_a_deleted_mapping_is_not_found(test_db_session):
    source_set, source_value = await _value_set(test_db_session, "VMDeleted_Source")
    target_set, target_value = await _value_set(test_db_session, "VMDeleted_Target")
    test_db_session.add(
        ValueSetValueMapping(SourceValueId=source_value.Id, TargetValueId=target_value.Id, Deleted=True)
    )
    await test_db_session.commit()

    assert await _ids(test_db_session, source_value_set_id=source_set.Id, target_value_set_id=target_set.Id) == []
