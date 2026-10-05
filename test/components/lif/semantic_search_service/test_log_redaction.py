"""
Semantic search keeps learner identifiers out of its logs (#1319).

In the Advisor flow the natural-language query carries the learner's identifier, and the
generated GraphQL embeds the filter as a literal. The test asserts that the search logged, and
that the identifier appears nowhere in the captured output.
"""

import logging
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
from pydantic import BaseModel

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
