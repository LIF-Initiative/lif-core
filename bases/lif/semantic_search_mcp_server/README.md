# `semantic_search_mcp_server` — Base

FastMCP-based [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that exposes LIF data via AI-callable tools. Designed for Claude, Cursor, and other MCP-aware clients to do semantic search over learner data fields without learning the GraphQL schema by hand.

## MCP tools
- `lif_query`    — semantic search over LIF data fields (translates natural-language fragments into GraphQL queries)
- `lif_mutation` — update LIF data fields (only registered when the schema includes a mutation model)

## HTTP endpoints (Starlette-mounted)
- `GET  /health`         — readiness check
- `GET  /schema/status`  — current schema source (`mdr` or `file`), leaf count, root types, filter models
- `POST /schema/refresh` — reload schema from MDR (state only — does not re-register MCP tools)

## Schema loading
At startup, loads the OpenAPI schema from MDR (with optional file fallback per `LIFSchemaConfig`). Uses `SchemaStateManager` to track source + provide thread-safe access. **No silent fallback in production:** if MDR is configured but unreachable, startup fails loudly rather than serving stale schema.

## Composes
- `lif_schema_config` — config + defaults
- `logging`
- `schema_state_manager` — schema lifecycle + refresh
- `semantic_search_service` — `run_semantic_search`, `run_mutation`

## Deployed as
`projects/lif_semantic_search_mcp_server/`
