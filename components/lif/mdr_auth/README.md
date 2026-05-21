# `mdr_auth` — Component

Authentication for the LIF Metadata Repository API. Provides the FastAPI middleware that handles three principal types in one place:

- **Service API-keys** — internal services (GraphQL, Translator, Semantic Search, Post-Confirmation Lambda) authenticate with `X-API-Key`.
- **Cognito JWT** — end users from the self-serve flow, validated against the user pool's JWKS.
- **Legacy HS256 JWT** — pre-Cognito callers (demo accounts, etc.), validated against the local shared secret.

The middleware also resolves `request.state.tenant_schema` per request based on the caller's `cognito:groups` claim and an optional workspace-selection cookie — see [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../../docs/design/cross-cutting/self-serve-tenant-auth.md).

## Public surface

```python
from lif.mdr_auth import (
    AuthMiddleware,
    create_access_token, create_refresh_token, decode_jwt,
)
```

`core.py` additionally exposes Cognito-side helpers (`decode_cognito_jwt`, `_get_cognito_jwk_client`) and config constants used by tests.

Phase 3 of issue #884 adds `workspace_cookie.py` (HMAC-signed workspace selection cookie) and `invite_token.py` (signed invite tokens for tenant sharing). Those land alongside the corresponding endpoint PRs (#914, #918).

## Used by
- `bases/lif/mdr_restapi` (mounts `AuthMiddleware`)
