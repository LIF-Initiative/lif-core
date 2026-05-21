# `mdr_client` — Component

HTTP client for the LIF Metadata Repository API. Used by every non-MDR service that needs to fetch the OpenAPI schema, data-model definitions, or transformation rules at startup or runtime.

Sends `X-API-Key` from the `LIF_MDR_API_AUTH_TOKEN` env var on every request when configured.

## Public surface

```python
from lif.mdr_client import (
    # Config-based (preferred)
    load_openapi_schema, fetch_schema_from_mdr,
    # File fallback
    get_openapi_lif_data_model_from_file,
    # Legacy env-var based functions
    get_openapi_lif_data_model, get_openapi_lif_data_model_sync,
    get_data_model_schema, get_data_model_schema_sync,
    get_data_model_transformation,
    # Exceptions
    MDRClientException, MDRConfigurationError,
)
```

`load_openapi_schema(config)` is the preferred entrypoint — it takes a `LIFSchemaConfig` and returns `(schema_dict, source)` where `source` is `"mdr"` or `"file"`. Callers should pass `LIFSchemaConfig.from_environment()` rather than threading individual env vars through.

**No silent fallback in production:** if MDR is configured but unreachable, `load_openapi_schema` fails with a clear error. Use `USE_OPENAPI_DATA_MODEL_FROM_FILE=true` (dev only) to opt into the bundled-file path.

## Bundled file

`resources/openapi_constrained_with_interactions.json` is the snapshot used by the file-fallback path. Kept in sync with MDR's V1.1 baseline; not the source of truth.

## Used by
- `bases/lif/api_graphql` — loads schema at startup, regenerates GraphQL types from it
- `components/lif/schema_state_manager` — wraps `load_openapi_schema` for services that need refresh + sync/async access
- `components/lif/translator` — fetches transformation definitions
