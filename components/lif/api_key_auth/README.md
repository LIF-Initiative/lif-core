# `api_key_auth` — Component

Simple API-key authentication middleware for FastAPI. Validates `X-API-Key` headers against a configurable map of `key:client-name` pairs, and exposes the matched client name on `request.state.principal`.

Used by services that want bare API-key auth (no Cognito, no HS256 JWT) — the GraphQL API in particular. For the richer MDR-side middleware that handles three principal types, see [`mdr_auth`](../mdr_auth/).

## Public surface

```python
from lif.api_key_auth import ApiKeyAuthMiddleware, ApiKeyConfig

config = ApiKeyConfig.from_environment(prefix="GRAPHQL_AUTH")
if config.is_enabled:
    app.add_middleware(ApiKeyAuthMiddleware, config=config)
```

The middleware no-ops when `<PREFIX>__API_KEYS` is unset, making local dev simple.

## Used by
- `bases/lif/api_graphql` — the GraphQL service's only auth path
