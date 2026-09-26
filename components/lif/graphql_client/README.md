# `graphql_client` — Component

Authenticated HTTP client for calling the LIF GraphQL API. Wraps the boilerplate (auth header, error mapping, JSON shaping) into two functions so callers don't need to learn `httpx` semantics.

## Public surface

```python
from lif.graphql_client import graphql_query, graphql_mutation, GraphQLClientException
```

Both functions send `X-API-Key` from `LIF_GRAPHQL_API_KEY` (when set) as the auth header — see CLAUDE.md § "GraphQL API Key Authentication" for the server-side configuration. They also always send `X-LIF-Client: semantic-search-mcp`, which GraphQL forwards so the Query Planner's statistics can tell this traffic apart (#1272).

| Function | Purpose |
|---|---|
| `graphql_query(...)` | Read-side query, returns parsed data |
| `graphql_mutation(...)` | Write-side mutation, returns parsed data |
| `GraphQLClientException` | Raised on transport or GraphQL-error response |

**A GraphQL error raises even on HTTP 200 (#1292).** A GraphQL server answers `200` for a failed operation and reports it in the body's `errors`, which is how the LIF GraphQL API has reported a Query Planner failure since #1264. Both functions raise `GraphQLClientException` with the error messages whenever `errors` is non-empty.

**Partial success raises too.** A body with both `data` and `errors` is not returned. The only caller selects a single root field (`person` or `updatePerson`), so a partial answer means a nested field failed, and handing back the rest would let that failure read as data the learner doesn't have. A caller that needs partial data would have to change this deliberately.

## Used by
- `components/lif/semantic_search_service` — calls GraphQL to fulfill MCP queries
