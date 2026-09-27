"""
GraphQL sends the Query Planner's API key on queries and mutations when one is configured (#1108).

The mutation resolver sent no headers at all before this, so once the planner enforces keys
every `update*` mutation would 401 -- the case a query-only test would miss.
"""

from lif.openapi_to_graphql import type_factory
from lif.openapi_to_graphql.core import generate_graphql_schema

from test.components.lif.openapi_to_graphql.test_lif_client_header import _CapturingAsyncClient

PERSON_QUERY = '{ person(filter: {name: "x"}) { name } }'
PERSON_MUTATION = 'mutation { updatePerson(filter: {name: "x"}, input: {name: "y"}) { name } }'


async def _headers_sent_to_the_planner(monkeypatch, document: str) -> dict:
    openapi = {
        "components": {
            "schemas": {
                "Person": {
                    "type": "array",
                    "properties": {
                        "name": {"DataType": "xsd:string", "Array": "No", "x-queryable": True, "x-mutable": True}
                    },
                }
            }
        }
    }
    schema = await generate_graphql_schema(
        openapi=openapi,
        root_type_name="Person",
        query_planner_query_url="http://localhost:9999/query",
        query_planner_update_url="http://localhost:9999/update",
    )
    fake = _CapturingAsyncClient()
    monkeypatch.setattr(type_factory.httpx, "AsyncClient", fake)
    # The canned response suits a query, not a mutation; only the outgoing headers matter here.
    await schema.execute(document)
    assert len(fake.sent_headers) == 1
    return fake.sent_headers[0]


async def test_query_sends_the_configured_key(monkeypatch):
    monkeypatch.setattr(type_factory, "LIF_QUERY_PLANNER_API_KEY", "qp-key")
    sent = await _headers_sent_to_the_planner(monkeypatch, PERSON_QUERY)
    assert sent == {"X-LIF-Client": "graphql", "X-API-Key": "qp-key"}


async def test_mutation_sends_the_configured_key(monkeypatch):
    monkeypatch.setattr(type_factory, "LIF_QUERY_PLANNER_API_KEY", "qp-key")
    sent = await _headers_sent_to_the_planner(monkeypatch, PERSON_MUTATION)
    assert sent == {"X-API-Key": "qp-key"}


async def test_no_key_is_sent_when_none_is_configured(monkeypatch):
    """An empty X-API-Key would 401 against an enforcing planner as surely as a missing one,
    but sending none keeps today's traffic byte-identical until a key is provisioned."""
    monkeypatch.setattr(type_factory, "LIF_QUERY_PLANNER_API_KEY", "")
    assert "X-API-Key" not in await _headers_sent_to_the_planner(monkeypatch, PERSON_QUERY)
    assert "X-API-Key" not in await _headers_sent_to_the_planner(monkeypatch, PERSON_MUTATION)
