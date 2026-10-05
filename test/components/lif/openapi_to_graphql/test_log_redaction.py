"""
GraphQL keeps learner identifiers and field values out of its logs (#1319).

#1269 stopped the Query Planner logging learner data, but GraphQL logged the planner's whole
response one hop later. Each test drives a path that logs, asserts that it did log, and asserts
that a known identifier and field value appear nowhere in the captured output.
"""

import dataclasses
import logging

import pytest

from lif.openapi_to_graphql import type_factory
from lif.openapi_to_graphql.core import generate_graphql_schema

IDENTIFIER = "SENTINEL-ID-4471"
FIELD_VALUE = "Marigold"
LOGGER = "lif.openapi_to_graphql.type_factory"


class _Response:
    status_code = 200
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient and answers every POST with one canned body."""

    def __init__(self, body):
        self._body = body

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        return _Response(self._body)


async def _schema():
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
    return await generate_graphql_schema(
        openapi=openapi,
        root_type_name="Person",
        query_planner_query_url="http://localhost:9999/query",
        query_planner_update_url="http://localhost:9999/update",
    )


def _our_log_text(caplog) -> str:
    # Only this module's records: Strawberry's own error log quotes the query document and is
    # tracked separately.
    return "\n".join(r.getMessage() for r in caplog.records if r.name == LOGGER)


def _assert_no_learner_data(caplog):
    text = _our_log_text(caplog)
    assert IDENTIFIER not in text
    assert FIELD_VALUE not in text


@pytest.mark.parametrize(
    "operation, planner_body, expected_log",
    [
        (
            f'{{ person(filter: {{name: "{IDENTIFIER}"}}) {{ name }} }}',
            [{"person": [{"name": FIELD_VALUE}]}],
            "Response:",
        ),
        (
            f'mutation {{ updatePerson(filter: {{name: "{IDENTIFIER}"}}, input: {{name: "{FIELD_VALUE}"}}) {{ name }} }}',
            {"person": [{"name": FIELD_VALUE}]},
            "Update mutation",
        ),
        (
            f'mutation {{ updatePerson(filter: {{name: "{IDENTIFIER}"}}, input: {{name: "x"}}) {{ name }} }}',
            {"unexpected": FIELD_VALUE},
            "Unexpected mutation response shape",
        ),
    ],
    ids=["query", "mutation", "unexpected-mutation-response"],
)
async def test_resolvers_log_no_learner_data(monkeypatch, caplog, operation, planner_body, expected_log):
    schema = await _schema()
    monkeypatch.setattr(type_factory.httpx, "AsyncClient", _FakeAsyncClient(planner_body))

    with caplog.at_level(logging.INFO, logger=LOGGER):
        await schema.execute(operation)

    assert expected_log in _our_log_text(caplog)
    _assert_no_learner_data(caplog)


@dataclasses.dataclass
class _Name:
    name: str


@dataclasses.dataclass
class _Rejecting:
    name: str

    def __post_init__(self):
        raise ValueError("rejected")


@pytest.mark.parametrize(
    "cls, data, expected_log",
    [(list[_Name], [FIELD_VALUE], "Failed to parse"), (_Rejecting, {"name": FIELD_VALUE}, "Failed to instantiate")],
    ids=["unparseable-list-item", "failed-instantiation"],
)
def test_dict_to_dataclass_warnings_log_no_learner_data(caplog, cls, data, expected_log):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        type_factory.dict_to_dataclass(cls, data)

    assert expected_log in _our_log_text(caplog)
    _assert_no_learner_data(caplog)
