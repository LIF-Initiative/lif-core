# `schema_state_manager` — Component

Thread-safe schema lifecycle manager for services that need the LIF schema at runtime *and* need to refresh it without restarting. Wraps [`mdr_client`](../mdr_client/) loading and [`openapi_schema_parser`](../openapi_schema_parser/) parsing into one object with sync + async init paths.

## Public surface

```python
from lif.schema_state_manager import SchemaStateManager, SchemaState
from lif.lif_schema_config import LIFSchemaConfig

config = LIFSchemaConfig.from_environment()
manager = SchemaStateManager(config)

# Sync (e.g., MCP server startup where async lifespan isn't an option)
manager.initialize_sync()

# Async (e.g., FastAPI lifespan)
await manager.initialize()

state = manager.state  # SchemaState — leaves, filter models, embeddings, source
await manager.refresh()  # re-load from MDR
```

`SchemaState` tracks where the schema came from (`"mdr"` or `"file"`) plus all the derived structures consumers need (parsed leaves, filter models, embeddings for semantic search).

## Used by
- `bases/lif/semantic_search_mcp_server` — initializes one manager at startup, exposes `POST /schema/refresh`
