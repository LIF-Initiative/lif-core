import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lif.datatypes import LIFRecord, LIFUpdate
from lif.datatypes.core import LIFUpdatePersonPayload
from lif.exceptions.core import ResourceNotFoundException
from lif.query_cache_service import core

PERSON_DOC = {"Person": [{"Name": [{"FamilyName": "Doe"}]}]}


def _patch_collection(mock_collection):
    return patch.object(core, "collection", mock_collection)


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
            filter={"Person": {"Identifier": {"identifier": "1"}}}, input={"Person": {"Name": {"FamilyName": "Doe"}}}
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
    assert args[1] == {"$set": {"Person.0.Name.FamilyName": "Doe"}}


def test_update_append_pushes_array_then_sets_then_reads_back():
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": "1"}}}, input={"Person": {"Name": {"GivenName": ["John"]}}}
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
        {"Person.Identifier.identifier": "1"}, {"$set": {"Person.0.Name.GivenName": []}}
    )
    mock_collection.find_one_and_update.assert_awaited_once()
    assert result.person.root == PERSON_DOC["Person"]


def test_update_no_match_raises_resource_not_found():
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": "missing"}}},
            input={"Person": {"Name": {"FamilyName": "Doe"}}},
        )
    )
    mock_collection = MagicMock()
    mock_collection.find_one_and_update = AsyncMock(return_value=None)

    with _patch_collection(mock_collection):
        with pytest.raises(ResourceNotFoundException):
            asyncio.run(core.update(lif_update))
