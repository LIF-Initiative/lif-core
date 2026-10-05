from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from lif.exceptions.core import InvalidInputException
from lif.query_cache_restapi import core


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
