"""
GraphQL relays the caller's X-LIF-Client to the Query Planner (#1272).

The MCP server reaches the planner only through GraphQL, so if GraphQL named itself on every
query the planner could never tell MCP traffic from any other GraphQL traffic. These tests
drive a real FastAPI app with Strawberry's GraphQLRouter -- mounted the way
`bases/lif/api_graphql/core.py` mounts it -- because the incoming request only reaches the
resolver through the router's default context. A schema executed directly never sees it.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from strawberry.fastapi import GraphQLRouter

from lif.openapi_to_graphql import type_factory
from lif.openapi_to_graphql.core import generate_graphql_schema

PERSON_QUERY = '{ person(filter: {name: "x"}) { name } }'


class _CapturingResponse:
    status_code = 200
    text = ""

    def json(self):
        return [{"person": []}]


class _CapturingAsyncClient:
    """Stands in for httpx.AsyncClient and records the headers of every POST to the planner."""

    def __init__(self):
        self.sent_headers: list[dict] = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self.sent_headers.append(headers or {})
        return _CapturingResponse()


async def _schema():
    openapi = {
        "components": {
            "schemas": {
                "Person": {
                    "type": "array",
                    "properties": {
                        "name": {"DataType": "xsd:string", "Array": "No", "x-queryable": True, "x-mutable": False}
                    },
                }
            }
        }
    }
    return await generate_graphql_schema(
        openapi=openapi,
        root_type_name="Person",
        query_planner_query_url="http://localhost:9999/query",
        query_planner_update_url="http://localhost:9999/update",
    )


async def _app(monkeypatch) -> FastAPI:
    app = FastAPI()
    app.include_router(GraphQLRouter(await _schema(), prefix="/graphql"))
    return app


async def _headers_sent_to_the_planner(monkeypatch, incoming: dict) -> dict:
    app = await _app(monkeypatch)
    fake = _CapturingAsyncClient()
    monkeypatch.setattr(type_factory.httpx, "AsyncClient", fake)
    response = TestClient(app).post("/graphql", json={"query": PERSON_QUERY}, headers=incoming)
    assert response.status_code == 200 and "errors" not in response.json(), response.text
    assert len(fake.sent_headers) == 1
    return fake.sent_headers[0]


async def test_forwards_the_callers_client_name(monkeypatch):
    sent = await _headers_sent_to_the_planner(monkeypatch, {"X-LIF-Client": "semantic-search-mcp"})
    assert sent["X-LIF-Client"] == "semantic-search-mcp"


async def test_names_itself_when_the_caller_did_not(monkeypatch):
    sent = await _headers_sent_to_the_planner(monkeypatch, {})
    assert sent["X-LIF-Client"] == "graphql"


async def test_relays_a_malformed_name_unchanged_for_the_planner_to_reject(monkeypatch):
    """Validation is the planner's, so it happens once, where the value is recorded."""
    sent = await _headers_sent_to_the_planner(monkeypatch, {"X-LIF-Client": "Not A Name"})
    assert sent["X-LIF-Client"] == "Not A Name"


async def test_a_schema_executed_without_a_request_still_names_itself(monkeypatch):
    schema = await _schema()
    fake = _CapturingAsyncClient()
    monkeypatch.setattr(type_factory.httpx, "AsyncClient", fake)
    result = await schema.execute(PERSON_QUERY)
    assert not result.errors, result.errors
    assert fake.sent_headers == [{"X-LIF-Client": "graphql"}]
