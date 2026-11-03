"""
Semantic search keeps learner identifiers out of its logs (#1319).

In the Advisor flow the natural-language query carries the learner's identifier, and the
generated GraphQL embeds the filter as a literal. The test asserts that the search logged, and
that the identifier appears nowhere in the captured output.
"""

import logging
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from lif.graphql_client.core import GraphQLClientException
from lif.openapi_schema_parser.core import SchemaLeaf
from lif.semantic_search_service import core

IDENTIFIER = "SENTINEL-ID-4471"


class _Filter(BaseModel):
    identifier: str


async def test_run_semantic_search_logs_no_identifier(caplog):
    model = Mock()
    model.encode = Mock(return_value=np.array([[1.0, 0.0]]))
    leaves = [
        SchemaLeaf(json_path="Person.Name.firstName", description="First name", attributes={}),
        SchemaLeaf(json_path="Person.Name.lastName", description="Last name", attributes={}),
    ]

    with (
        patch.object(core, "execute_graphql_query", AsyncMock(return_value={"data": {}})),
        caplog.at_level(logging.INFO, logger="lif.semantic_search_service.core"),
    ):
        await core.run_semantic_search(
            filter=_Filter(identifier=IDENTIFIER),
            query=f"What is the first name of learner {IDENTIFIER}?",
            model=model,
            embeddings=np.array([[1.0, 0.0], [0.0, 1.0]]),
            leaves=leaves,
            top_k=1,
            graphql_url="http://localhost:9999/graphql",
        )

    assert "Generated GraphQL" in caplog.text
    assert IDENTIFIER not in caplog.text


# #1351: a failed GraphQL call. The client's exception message can carry the error body or a
# GraphQL error quoting a learner value. The MCP caller still gets it; the log gets the type.


def _run_query():
    model = Mock()
    model.encode = Mock(return_value=np.array([[1.0, 0.0]]))
    leaves = [SchemaLeaf(json_path="Person.Name.firstName", description="First name", attributes={})]
    return core.run_semantic_search(
        filter=_Filter(identifier=IDENTIFIER),
        query="What is the first name?",
        model=model,
        embeddings=np.array([[1.0, 0.0]]),
        leaves=leaves,
        top_k=1,
        graphql_url="http://localhost:9999/graphql",
    )


def _run_mutation():
    return core.run_mutation(
        filter=_Filter(identifier=IDENTIFIER),
        input=_Filter(identifier="x"),
        graphql_url="http://localhost:9999/graphql",
    )


@pytest.mark.parametrize("error_type", [GraphQLClientException, ValueError])
@pytest.mark.parametrize(
    "run, client_function",
    [(_run_query, "execute_graphql_query"), (_run_mutation, "execute_graphql_mutation")],
    ids=["query", "mutation"],
)
async def test_a_failed_graphql_call_logs_no_identifier(caplog, run, client_function, error_type):
    error = error_type(f"GraphQL HTTP error 422: {IDENTIFIER}")
    with (
        patch.object(core, client_function, AsyncMock(side_effect=error)),
        caplog.at_level(logging.INFO, logger="lif.semantic_search_service.core"),
        pytest.raises(ToolError) as raised,
    ):
        await run()

    assert f"tool error: {error_type.__name__}" in caplog.text
    assert IDENTIFIER not in caplog.text
    assert IDENTIFIER in str(raised.value)
