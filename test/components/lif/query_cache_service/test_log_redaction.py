"""
The Query Cache keeps learner identifiers and field values out of its logs (#1319).

Each test drives a path that logs, asserts that it did log, and asserts that a known identifier
and field value appear nowhere in the captured output.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from lif.datatypes import LIFPersonIdentifier, LIFPersonIdentifiers, LIFQuery, LIFQueryFilter, LIFQueryPersonFilter
from lif.datatypes import LIFRecord, LIFUpdate
from lif.datatypes.core import LIFUpdatePersonPayload
from lif.query_cache_service import core

IDENTIFIER = "SENTINEL-ID-4471"
FIELD_VALUE = "Marigold"
LOGGER = "lif.query_cache_service.core"
PERSON_DOC = {"Person": [{"Identifier": [{"identifier": IDENTIFIER}], "Name": [{"FamilyName": FIELD_VALUE}]}]}


def _async_cursor(docs):
    cursor = MagicMock()
    cursor.__aiter__.return_value = docs
    return cursor


def _assert_logged_without_learner_data(caplog, expected_log):
    assert expected_log in caplog.text
    assert IDENTIFIER not in caplog.text
    assert FIELD_VALUE not in caplog.text


async def test_query_logs_no_learner_data(caplog):
    query = LIFQuery(
        filter=LIFQueryFilter(
            root=LIFQueryPersonFilter(
                person=LIFPersonIdentifiers(
                    Identifier=LIFPersonIdentifier(identifier=IDENTIFIER, identifierType="School-assigned number")
                )
            )
        ),
        selected_fields=["Person.Name"],
    )
    mock_collection = MagicMock()
    mock_collection.find = MagicMock(return_value=_async_cursor([PERSON_DOC]))

    with patch.object(core, "collection", mock_collection), caplog.at_level(logging.INFO, logger=LOGGER):
        await core.query(query)

    _assert_logged_without_learner_data(caplog, "QUERY CACHE RETURNING")


async def test_update_logs_no_learner_data(caplog):
    lif_update = LIFUpdate(
        updatePerson=LIFUpdatePersonPayload(
            filter={"Person": {"Identifier": {"identifier": IDENTIFIER}}},
            # A list under the entity: an object under it is refused before any log line (#1356).
            input={"Person": {"Name": [{"familyName": FIELD_VALUE}]}},
        )
    )
    mock_collection = MagicMock()
    # A list under an entity reads the current document and initializes the array before the update.
    mock_collection.find_one = AsyncMock(return_value=PERSON_DOC)
    mock_collection.update_one = AsyncMock()
    mock_collection.find_one_and_update = AsyncMock(return_value=PERSON_DOC)

    with patch.object(core, "collection", mock_collection), caplog.at_level(logging.INFO, logger=LOGGER):
        await core.update(lif_update)

    _assert_logged_without_learner_data(caplog, "UPDATE DOC")


async def test_add_logs_no_learner_data(caplog):
    record = LIFRecord(person=PERSON_DOC["Person"])
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id="abc"))

    with patch.object(core, "collection", mock_collection), caplog.at_level(logging.INFO, logger=LOGGER):
        await core.add(lif_record=record)

    _assert_logged_without_learner_data(caplog, "CALL MADE TO ADD")
