import asyncio

from lif.graphql.schema_factory import build_schema


class FakeBackend:
    async def query(self, filter_dict, selected_fields):
        return []

    async def update(self, filter_dict, input_dict, selected_fields):
        return []


def test_build_schema_smoke(monkeypatch):
    # Configure dynamic models to read our small test schema
    monkeypatch.setenv("OPENAPI_SCHEMA_FILE", "test_openapi_schema.json")
    monkeypatch.setenv("ROOT_NODE", "Person")

    schema = build_schema(root_node="Person", backend=FakeBackend())
    s = schema.as_str()
    assert "type Query" in s
    assert "type Mutation" in s


def test_execute_query_smoke(monkeypatch):
    monkeypatch.setenv("OPENAPI_SCHEMA_FILE", "test_openapi_schema.json")
    monkeypatch.setenv("ROOT_NODE", "Person")

    class CapturingBackend(FakeBackend):
        def __init__(self):
            self.seen = []

        async def query(self, filter_dict, selected_fields):
            self.seen.append((filter_dict, tuple(selected_fields)))
            return []

    backend = CapturingBackend()
    schema = build_schema(root_node="Person", backend=backend)

    query = """
    query Q($f: PersonFilterInput!) {
      persons(filter: $f) { person { identifier name } }
    }
    """
    variables = {"f": {"person": {"identifier": "123"}}}
    result = asyncio.run(schema.execute(query, variable_values=variables))
    assert result.errors is None
    assert backend.seen, "backend was not called"
