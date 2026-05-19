# `graphql_client` — Component

Authenticated HTTP client for calling the LIF GraphQL API. Wraps the boilerplate (auth header, error mapping, JSON shaping) into two functions so callers don't need to learn `httpx` semantics.

## Public surface

```python
from lif.graphql_client import graphql_query, graphql_mutation, GraphQLClientException
```

Both functions send `X-API-Key` from `LIF_GRAPHQL_API_KEY` (when set) as the auth header — see CLAUDE.md § "GraphQL API Key Authentication" for the server-side configuration.

| Function | Purpose |
|---|---|
| `graphql_query(...)` | Read-side query, returns parsed data |
| `graphql_mutation(...)` | Write-side mutation, returns parsed data |
| `GraphQLClientException` | Raised on transport or GraphQL-error response |

## Used by
- `components/lif/semantic_search_service` — calls GraphQL to fulfill MCP queries
