import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lif.datatypes import (
    LIFFragment,
    LIFPersonIdentifier,
    LIFPersonIdentifiers,
    LIFQueryFilter,
    LIFQueryPersonFilter,
    LIFRecord,
    LIFUpdate,
)
from lif.datatypes.core import LIFUpdatePersonPayload
from lif.exceptions.core import InvalidInputException, ResourceNotFoundException
from lif.query_cache_service import core

PERSON_DOC = {"Person": [{"Name": [{"FamilyName": "Doe"}]}]}


def _patch_collection(mock_collection):
    return patch.object(core, "collection", mock_collection)


def _async_cursor(docs):
    cursor = MagicMock()
    cursor.__aiter__.return_value = docs
    return cursor


def _query_filter(identifier="12345", identifier_type="School-assigned number"):
    return LIFQueryFilter(
        root=LIFQueryPersonFilter(
            person=LIFPersonIdentifiers(
                Identifier=LIFPersonIdentifier(identifier=identifier, identifierType=identifier_type)
            )
        )
    )


def _name_fragment(family_name="Smith"):
    return LIFFragment(fragment_path="Person.Name", fragment=[{"FamilyName": family_name}])


def test_add_makes_single_mongodb_call_and_returns_input_record():
    record = LIFRecord(person=[{"Name": [{"FamilyName": "Doe"}]}])
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id="abc"))

    with _patch_collection(mock_collection):
        result = asyncio.run(core.add(lif_record=record))

    mock_collection.insert_one.assert_awaited_once_with(record.model_dump(by_alias=True))
    mock_collection.find_one.assert_not_called()
    assert result == record


def test_add_raises_when_no_inserted_id():
    record = LIFRecord(person=[{"Name": [{"FamilyName": "Doe"}]}])
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=None))

    with _patch_collection(mock_collection):
        with pytest.raises(ResourceNotFoundException):
            asyncio.run(core.add(lif_record=record))

    mock_collection.insert_one.assert_awaited_once()
    mock_collection.find_one.assert_not_called()


def test_update_set_only_uses_single_find_one_and_update():
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": "1"}}}, input={"Person": {"nickname": "Doe"}}
        )
    )
    mock_collection = MagicMock()
    mock_collection.find_one_and_update = AsyncMock(return_value=PERSON_DOC)

    with _patch_collection(mock_collection):
        result = asyncio.run(core.update(lif_update))

    mock_collection.find_one_and_update.assert_awaited_once()
    mock_collection.update_one.assert_not_called()
    mock_collection.find_one.assert_not_called()
    assert result.person.root == PERSON_DOC["Person"]

    args, kwargs = mock_collection.find_one_and_update.await_args
    assert kwargs["projection"] == {"Person": 1, "_id": 0}
    assert kwargs["return_document"] == core.ReturnDocument.AFTER
    assert args[0] == {"Person.Identifier.identifier": "1"}
    assert args[1] == {"$set": {"Person.0.nickname": "Doe"}}


def test_update_append_pushes_array_then_sets_then_reads_back():
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": "1"}}},
            input={"Person": {"Proficiency": [{"name": "Welding"}]}},
        )
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value={})  # current doc lacks the array
    mock_collection.update_one = AsyncMock(return_value=MagicMock())
    mock_collection.find_one_and_update = AsyncMock(return_value=PERSON_DOC)

    with _patch_collection(mock_collection):
        result = asyncio.run(core.update(lif_update))

    mock_collection.find_one.assert_awaited_once()
    # array init for missing array
    mock_collection.update_one.assert_awaited_once_with(
        {"Person.Identifier.identifier": "1"}, {"$set": {"Person.0.Proficiency": []}}
    )
    mock_collection.find_one_and_update.assert_awaited_once_with(
        {"Person.Identifier.identifier": "1"},
        {"$push": {"Person.0.Proficiency": {"name": "Welding"}}},
        projection={"Person": 1, "_id": 0},
        return_document=core.ReturnDocument.AFTER,
    )
    assert result.person.root == PERSON_DOC["Person"]

    # The array init must precede the $push -- MongoDB $push fails against a non-array field.
    assert [c[0] for c in mock_collection.mock_calls] == ["find_one", "update_one", "find_one_and_update"]


def test_update_append_multiple_elements_wraps_them_in_each():
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": "1"}}},
            input={"Person": {"Proficiency": [{"name": "Welding"}, {"name": "Brazing"}]}},
        )
    )
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value={})  # current doc lacks the array
    mock_collection.update_one = AsyncMock(return_value=MagicMock())
    mock_collection.find_one_and_update = AsyncMock(return_value=PERSON_DOC)

    with _patch_collection(mock_collection):
        asyncio.run(core.update(lif_update))

    # A multi-element append must go through $each; without it MongoDB pushes the
    # list itself as a single nested element.
    mock_collection.find_one_and_update.assert_awaited_once_with(
        {"Person.Identifier.identifier": "1"},
        {"$push": {"Person.0.Proficiency": {"$each": [{"name": "Welding"}, {"name": "Brazing"}]}}},
        projection={"Person": 1, "_id": 0},
        return_document=core.ReturnDocument.AFTER,
    )


def test_update_no_match_raises_resource_not_found():
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": "missing"}}}, input={"Person": {"nickname": "Doe"}}
        )
    )
    mock_collection = MagicMock()
    mock_collection.find_one_and_update = AsyncMock(return_value=None)

    with _patch_collection(mock_collection):
        with pytest.raises(ResourceNotFoundException):
            asyncio.run(core.update(lif_update))


def test_save_reads_record_then_upserts_in_two_calls():
    """save() composes fragments client-side, so it needs one read plus one upsert."""
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=_async_cursor([PERSON_DOC]))
    mock_collection.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=0))

    with _patch_collection(mock_collection):
        asyncio.run(core.save(lif_query_filter=_query_filter(), lif_fragments=[_name_fragment()]))

    mongo_filter = {
        "Person.Identifier.identifier": "12345",
        "Person.Identifier.identifierType": "School-assigned number",
    }
    mock_collection.find.assert_called_once_with(mongo_filter)
    mock_collection.update_one.assert_awaited_once_with(
        mongo_filter, {"$set": {"Person": [{"Name": [{"FamilyName": "Smith"}]}]}}, upsert=True
    )


def test_save_upserts_fresh_record_when_none_found():
    """When no record matches, save() builds one carrying the identifier plus fragments."""
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=_async_cursor([]))
    mock_collection.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=0))

    with _patch_collection(mock_collection):
        asyncio.run(core.save(lif_query_filter=_query_filter("999"), lif_fragments=[_name_fragment()]))

    mongo_filter = {"Person.Identifier.identifier": "999", "Person.Identifier.identifierType": "School-assigned number"}
    mock_collection.update_one.assert_awaited_once_with(
        mongo_filter,
        {
            "$set": {
                "Person": [
                    {
                        "Identifier": {"identifier": "999", "identifierType": "School-assigned number"},
                        "Name": [{"FamilyName": "Smith"}],
                    }
                ]
            }
        },
        upsert=True,
    )


def test_save_raises_when_filter_matches_multiple_records():
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=_async_cursor([PERSON_DOC, PERSON_DOC]))
    mock_collection.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=0))

    with _patch_collection(mock_collection):
        with pytest.raises(ValueError):
            asyncio.run(core.save(lif_query_filter=_query_filter(), lif_fragments=[_name_fragment()]))

    mock_collection.update_one.assert_not_awaited()


def test_save_replaces_existing_fragment_data_instead_of_appending():
    """A second refresh over the same fragments must not re-add them (Issue #1165)."""
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=_async_cursor([]))
    written_records = []

    async def _update_one(mongo_filter, update_doc, upsert=True):
        written_records.append(update_doc["$set"])
        mock_collection.find.return_value = _async_cursor([update_doc["$set"]])
        return SimpleNamespace(modified_count=0)

    mock_collection.update_one = AsyncMock(side_effect=_update_one)

    fragment = _name_fragment()
    with _patch_collection(mock_collection):
        for _ in range(2):
            asyncio.run(core.save(lif_query_filter=_query_filter(), lif_fragments=[fragment]))

    persisted_name = written_records[1]["Person"][0]["Name"]
    assert persisted_name == [{"FamilyName": "Smith"}]


# -------------------------------------------------------------------------
# #1229 — an object under an entity has no element to land in. Every
# PascalCase entity is an array (docs/specs/data-model-rules.md), so
# "Person.0.Name.lastName" names no element and MongoDB rejects it. It is
# refused before any MongoDB call instead of surfacing as a 500.
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "update_input",
    [
        {"Person": {"Name": {"lastName": "Renamed"}}},  # $set inside an entity
        {"Person": {"Name": {"GivenName": ["John"]}}},  # $push under an object under an entity
        {"Person": {"nickname": "Writey", "Contact": {"Email": {"emailAddress": "a@b.c"}}}},  # mixed with a valid field
    ],
)
def test_update_refuses_an_object_under_an_entity_before_touching_mongodb(update_input):
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(filter={"Person": {"Identifier": {"identifier": "1"}}}, input=update_input)
    )
    mock_collection = MagicMock()

    with _patch_collection(mock_collection):
        with pytest.raises(InvalidInputException) as exc_info:
            asyncio.run(core.update(lif_update))

    assert mock_collection.mock_calls == []
    entity = next(k for k, v in update_input["Person"].items() if isinstance(v, dict))
    assert entity in str(exc_info.value)


def test_update_still_sets_an_object_under_a_camelcase_attribute():
    """Only PascalCase keys are entities; a camelCase attribute holding an object is not an array."""
    set_ops, push_ops = core.build_mongo_update_ops({"nickname": {"display": "W"}})

    assert set_ops == {"Person.0.nickname.display": "W"}
    assert push_ops == {}
