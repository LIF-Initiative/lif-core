# Semantic Search MCP Server

The semantic search service (`bases/lif/semantic_search_mcp_server/`) provides MCP tools for AI-powered learner data queries.

**Architecture:**
- Uses FastMCP for Model Context Protocol
- Loads schema from MDR at startup (sync initialization required for tool registration) — see [`schema-loading.md`](../cross-cutting/schema-loading.md)
- Connected to org1's GraphQL API for data queries
- Embeddings computed via Sentence-Transformers

**HTTP Endpoints:**
- `GET /health` - Readiness check
- `GET /schema/status` - Schema metadata (source, leaf count, roots, filter models)
- `POST /schema/refresh` - Reload schema from MDR (state only, not tool definitions)

**MCP Tools:**
- `lif_query` - Semantic search over LIF data fields
- `lif_mutation` - Update LIF data fields (if mutation model available)

**Docker port:** 8003 (exposed for integration testing)

**Retrieval tuning:** the #715 study measured this service's retrieval path end-to-end — recall@k against `SEMANTIC_SEARCH__TOP_K=200`, leaf-description quality as the binding constraint, and the top_k-before-filter ordering in `semantic_search_service/core.py`. Findings F1/F2/F3/F6 and recommendations R2/R3/R4 are written up in [`advisor-api.md`](advisor-api.md#possible-future-roadmap-items).

**GraphQL authentication:** Uses `graphql_client` component for all GraphQL HTTP calls, which automatically sends `X-API-Key` from the `LIF_GRAPHQL_API_KEY` env var when set. See [`graphql-api-keys.md`](../../operations/guides/graphql-api-keys.md).
