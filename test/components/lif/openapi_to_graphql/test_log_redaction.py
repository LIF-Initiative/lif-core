"""
GraphQL keeps learner identifiers and field values out of its logs (#1319).

#1269 stopped the Query Planner logging learner data, but GraphQL logged the planner's whole
response one hop later. Each test drives a path that logs, asserts that it did log, and asserts
that a known identifier and field value appear nowhere in the captured output.
"""

import dataclasses
import datetime
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
    # Only this module's records. The failure-path tests below check every logger, Strawberry's too.
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


# #1351: the failure paths. Strawberry's own error log quoted the query document (which holds the
# identifier) and the error message (which can hold a learner value), so these check every
# logger's output, tracebacks included.


class _ErrorResponse(_Response):
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class _FailingAsyncClient(_FakeAsyncClient):
    """Answers every POST with an error status, as the Query Planner does when a request fails."""

    def __init__(self, status_code, text):
        self._status_code = status_code
        self._text = text

    async def post(self, url, json=None, headers=None):
        return _ErrorResponse(self._status_code, self._text)


def _assert_no_learner_data_anywhere(caplog):
    # caplog.text is every logger's formatted output, including exception tracebacks.
    assert IDENTIFIER not in caplog.text
    assert FIELD_VALUE not in caplog.text


# FastAPI's 422 body echoes the request input, so the Query Planner's error body can hold the filter.
_ECHOED_422 = f'{{"detail": [{{"type": "missing", "input": {{"name": "{IDENTIFIER}"}}}}]}}'


@pytest.mark.parametrize(
    "operation",
    [
        f'{{ person(filter: {{name: "{IDENTIFIER}"}}) {{ name }} }}',
        f'mutation {{ updatePerson(filter: {{name: "{IDENTIFIER}"}}, input: {{name: "x"}}) {{ name }} }}',
    ],
    ids=["query", "mutation"],
)
async def test_planner_failure_logs_no_learner_data(monkeypatch, caplog, operation):
    schema = await _schema()
    monkeypatch.setattr(type_factory.httpx, "AsyncClient", _FailingAsyncClient(422, _ECHOED_422))

    with caplog.at_level(logging.INFO):
        result = await schema.execute(operation)

    assert result.errors
    assert "failed: 422" in _our_log_text(caplog)
    assert any(r.name == "strawberry.execution" and r.levelno == logging.ERROR for r in caplog.records)
    _assert_no_learner_data_anywhere(caplog)


@pytest.mark.parametrize(
    "planner_body",
    [
        # dict_to_dataclass's TypeError quoted the value.
        [{"person": [FIELD_VALUE]}],
        # graphql-core's serialization error quotes the value, and we can't change its message.
        [{"person": [{"name": [FIELD_VALUE]}]}],
    ],
    ids=["unconvertible-record", "unserializable-field"],
)
async def test_resolver_error_logs_no_learner_data(monkeypatch, caplog, planner_body):
    schema = await _schema()
    monkeypatch.setattr(type_factory.httpx, "AsyncClient", _FakeAsyncClient(planner_body))

    with caplog.at_level(logging.INFO):
        result = await schema.execute(f'{{ person(filter: {{name: "{IDENTIFIER}"}}) {{ name }} }}')

    assert result.errors
    strawberry_logs = [r for r in caplog.records if r.name == "strawberry.execution"]
    assert strawberry_logs
    # Still useful for debugging: the GraphQL path and the raising frame.
    assert "GraphQL error at ['person'" in strawberry_logs[0].getMessage()
    assert 'File "' in strawberry_logs[0].getMessage()
    _assert_no_learner_data_anywhere(caplog)


def test_unconvertible_record_error_omits_the_value():
    with pytest.raises(TypeError) as raised:
        type_factory.dict_to_dataclass(_Name, FIELD_VALUE)

    assert FIELD_VALUE not in str(raised.value)


@dataclasses.dataclass
class _Born:
    birth_date: datetime.date


def test_unparseable_field_warning_logs_no_learner_data(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        result = type_factory.dict_to_dataclass(_Born, {"birth_date": FIELD_VALUE})

    assert result == _Born(birth_date=None)
    assert "Error in field 'birth_date'" in _our_log_text(caplog)
    _assert_no_learner_data(caplog)
