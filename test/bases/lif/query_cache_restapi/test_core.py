import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure

from lif.datatypes import LIFPersonIdentifier, LIFPersonIdentifiers, LIFQueryFilter, LIFQueryPersonFilter
from lif.exceptions.core import InvalidInputException
from lif.query_cache_restapi import core
from lif.query_cache_service import core as service_core


def test_sample():
    assert core is not None


def test_update_answers_422_for_invalid_input():
    """#1229: an update MongoDB cannot apply is the caller's error, not a 500."""
    message = "Cannot set fields inside entity 'Name'"
    payload = {"updatePerson": {"filter": {"Person": {"Identifier": {"identifier": "1"}}}, "input": {"Person": {}}}}
    with patch.object(core, "update", AsyncMock(side_effect=InvalidInputException(message))):
        response = TestClient(core.app).post("/update", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == message


# -------------------------------------------------------------------------
# #1360: a 404 or 500 answers with fixed text, and the failure is still logged.
# A Mongo error's message can quote the document, and the API returned it as the body.
# These run the real service against a stubbed collection, so the service's own log is checked too.
# -------------------------------------------------------------------------
SENTINEL = "SENTINEL-NAME-4471"
SERVICE_LOGGER = "lif.query_cache_service.core"
_MONGO_ERROR = OperationFailure(f'Document failed validation: {{ firstName: "{SENTINEL}" }}')
_FILTER = LIFQueryFilter(
    root=LIFQueryPersonFilter(
        person=LIFPersonIdentifiers(
            Identifier=LIFPersonIdentifier(identifier=SENTINEL, identifierType="School-assigned number")
        )
    )
).model_dump(mode="json", by_alias=True)
_UPDATE = {
    "updatePerson": {
        "filter": {"Person": {"Identifier": {"identifier": SENTINEL}}},
        "input": {"Person": {"nickname": "x"}},
    }
}
_RECORD = {"Person": [{"Identifier": [{"identifier": SENTINEL}]}]}


def _post(path, payload, collection, caplog):
    with patch.object(service_core, "collection", collection), caplog.at_level(logging.ERROR, logger=SERVICE_LOGGER):
        return TestClient(core.app).post(path, json=payload)


def _assert_fixed_response(response, status_code, detail, caplog, logged):
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert SENTINEL not in response.text
    # Replacing the body must not drop the error: the service logs its type and stack.
    assert logged in caplog.text
    assert SENTINEL not in caplog.text


@pytest.mark.parametrize(
    "path, payload, method, detail, logged",
    [
        (
            "/query",
            {"filter": _FILTER, "selected_fields": ["Person.Name"]},
            "find",
            "Error processing query",
            "Query Exception: OperationFailure",
        ),
        ("/update", _UPDATE, "find_one_and_update", "Error processing update", "Update Exception: OperationFailure"),
        ("/add", _RECORD, "insert_one", "Error adding record", "Add Exception: OperationFailure"),
        (
            "/save",
            {"lif_query_filter": _FILTER, "lif_fragments": []},
            "find",
            "Error saving record",
            "Save Exception: OperationFailure",
        ),
    ],
)
def test_a_500_does_not_return_the_error_message(path, payload, method, detail, logged, caplog):
    collection = MagicMock()
    # find is synchronous on the async client (it returns a cursor); the others are awaited.
    setattr(
        collection,
        method,
        MagicMock(side_effect=_MONGO_ERROR) if method == "find" else AsyncMock(side_effect=_MONGO_ERROR),
    )

    response = _post(path, payload, collection, caplog)

    _assert_fixed_response(response, 500, detail, caplog, logged)


def test_update_with_no_match_answers_a_fixed_404(caplog):
    collection = MagicMock()
    collection.find_one_and_update = AsyncMock(return_value=None)

    response = _post("/update", _UPDATE, collection, caplog)

    _assert_fixed_response(
        response, 404, "No matching record after update", caplog, "Update Exception: ResourceNotFoundException"
    )


def test_add_with_no_inserted_id_answers_a_fixed_404(caplog):
    collection = MagicMock()
    collection.insert_one = AsyncMock(return_value=SimpleNamespace(inserted_id=None))

    response = _post("/add", _RECORD, collection, caplog)

    _assert_fixed_response(
        response,
        404,
        "Failed to add record, no inserted ID returned",
        caplog,
        "Add Exception: ResourceNotFoundException",
    )


# A ValueError used to be re-raised out of the app. The client got a plain 500, but uvicorn then
# logged "Exception in ASGI application" with the message, and a pydantic ValidationError quotes the input.
# TestClient re-raises whatever escapes the app, so these fail if the error escapes.
@pytest.mark.parametrize(
    "path, payload, service_function, detail",
    [
        ("/query", {"filter": _FILTER, "selected_fields": ["Person.Name"]}, "query", "Error processing query"),
        ("/update", _UPDATE, "update", "Error processing update"),
        ("/add", _RECORD, "add", "Error adding record"),
        ("/save", {"lif_query_filter": _FILTER, "lif_fragments": []}, "save", "Error saving record"),
    ],
)
def test_a_value_error_answers_the_fixed_500_instead_of_escaping(path, payload, service_function, detail):
    with patch.object(core, service_function, AsyncMock(side_effect=ValueError(f"bad value {SENTINEL}"))):
        response = TestClient(core.app).post(path, json=payload)

    assert response.status_code == 500
    assert response.json() == {"detail": detail}


def test_a_stored_record_that_fails_validation_answers_a_fixed_500(caplog):
    """The case from the #1454 review: the record Mongo returns fails LIFRecord's validation."""
    collection = MagicMock()
    collection.find_one_and_update = AsyncMock(return_value={"Person": SENTINEL})

    response = _post("/update", _UPDATE, collection, caplog)

    _assert_fixed_response(response, 500, "Error processing update", caplog, "Update Exception: ValidationError")
