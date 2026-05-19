# `semantic_search_service` — Component

Implements the semantic search and mutation operations that the MCP server exposes as tools. Given a natural-language fragment, finds the closest matching LIF data fields (via Sentence-Transformers embeddings over schema leaves) and constructs the corresponding GraphQL query or mutation.

## Public surface

```python
from lif.semantic_search_service.core import run_semantic_search, run_mutation
```

| Function | Purpose |
|---|---|
| `run_semantic_search(query, ...)` | Translate a NL fragment into a GraphQL query, execute it, return results |
| `run_mutation(...)` | Same idea for mutations (only registered if the schema has a mutation model) |

Both dispatch through [`graphql_client`](../graphql_client/) so the same authentication / error-handling rules apply.

## Used by
- `bases/lif/semantic_search_mcp_server` — both functions are wrapped as MCP tools (`lif_query`, `lif_mutation`)
- `components/lif/schema_state_manager` — used during initialization to build embeddings for the leaves it caches
