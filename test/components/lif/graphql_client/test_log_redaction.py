"""
The GraphQL client keeps learner data out of its logs (#1351).

An error body can echo the request (FastAPI's 422 quotes its input), and GraphQL error messages
can quote a learner value (graphql-core's "String cannot represent value: ..."). The log gets the
status, sizes and types. The raised message is unchanged: semantic search hands it to the MCP
caller, which uses GraphQL's error text to correct its query.
"""

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from lif.graphql_client import core
from lif.graphql_client.core import GraphQLClientException

IDENTIFIER = "SENTINEL-ID-4471"
FIELD_VALUE = "Marigold"
URL = "http://localhost:8000/graphql"
OPERATIONS = [core.graphql_query, core.graphql_mutation]


def _response(status_code: int, text: str) -> httpx.Response:
    return httpx.Response(status_code, text=text, request=httpx.Request("POST", URL))


@pytest.mark.parametrize("operation", OPERATIONS, ids=["query", "mutation"])
async def test_an_error_body_is_not_logged(caplog, operation):
    body = f'{{"detail": [{{"input": {{"identifier": "{IDENTIFIER}"}}}}]}}'
    with (
        patch.object(core, "_post", AsyncMock(return_value=_response(422, body))),
        caplog.at_level(logging.INFO),
        pytest.raises(GraphQLClientException) as raised,
    ):
        await operation(query="{ x }", url=URL)

    assert "GraphQL HTTP error 422" in caplog.text
    assert IDENTIFIER not in caplog.text
    assert IDENTIFIER in str(raised.value)


@pytest.mark.parametrize("operation", OPERATIONS, ids=["query", "mutation"])
async def test_graphql_error_messages_are_not_logged(caplog, operation):
    body = f'{{"data": null, "errors": [{{"message": "String cannot represent value: [\'{FIELD_VALUE}\']"}}]}}'
    with (
        patch.object(core, "_post", AsyncMock(return_value=_response(200, body))),
        caplog.at_level(logging.INFO),
        pytest.raises(GraphQLClientException) as raised,
    ):
        await operation(query="{ x }", url=URL)

    assert "1 GraphQL error(s)" in caplog.text
    assert FIELD_VALUE not in caplog.text
    assert FIELD_VALUE in str(raised.value)


@pytest.mark.parametrize("operation", OPERATIONS, ids=["query", "mutation"])
async def test_a_client_error_message_is_not_logged(caplog, operation):
    with (
        patch.object(core, "_post", AsyncMock(side_effect=ValueError(f"rejected {IDENTIFIER}"))),
        caplog.at_level(logging.INFO),
        pytest.raises(GraphQLClientException),
    ):
        await operation(query="{ x }", url=URL)

    assert "GraphQL client error: ValueError" in caplog.text
    assert IDENTIFIER not in caplog.text
