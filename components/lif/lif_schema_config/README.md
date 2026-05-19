# `lif_schema_config` — Component

Centralized configuration and utility helpers for everything LIF services do with the schema: where to load it from, how to name GraphQL types from it, how to map XSD types into Python.

Replaces scattered `os.getenv("LIF_…")` calls across services with a single `LIFSchemaConfig` that knows how to read from the environment and validate.

## Layout

| File | Contents |
|---|---|
| `core.py` | `LIFSchemaConfig` — the main config class + `from_environment()` factory |
| `type_mappings.py` | XSD → Python type conversions used by schema generation |
| `naming.py` | Case conversion + GraphQL naming conventions (PascalCase / camelCase rules) |
| `openapi.py` | OpenAPI document structure helpers |
| Also exports | `DEFAULT_ATTRIBUTE_KEYS` — common attribute keys used by semantic search |

## Public surface

```python
from lif.lif_schema_config import LIFSchemaConfig, DEFAULT_ATTRIBUTE_KEYS

config = LIFSchemaConfig.from_environment()
config.root_type_name        # "Person"
config.graphql_query_name    # "person"
config.mdr_api_url           # URL of MDR API
config.query_planner_query_url
```

## Used by
- `bases/lif/api_graphql`
- `bases/lif/semantic_search_mcp_server`
- `components/lif/query_cache_service`
- `components/lif/openapi_to_graphql`
- `components/lif/semantic_search_service`
