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

HS256 signing/decoding, bearer extraction, the `X-API-Key` header name, and the public-path check come from [`auth_utils`](../auth_utils/). Cognito JWT validation is delegated to [`cognito_auth`](../cognito_auth/); `core.py` builds its `CognitoAuthConfig` (`COGNITO_CONFIG`) from MDR settings. If `MDR__AUTH__COGNITO_USER_POOL_ID` is set but `MDR__AUTH__COGNITO_SPA_CLIENT_ID` is empty, the module fails at import rather than accepting tokens from any app client in the pool.

Phase 3 of issue #884 adds `workspace_cookie.py` (HMAC-signed workspace selection cookie) and `invite_token.py` (signed invite tokens for tenant sharing). Those land alongside the corresponding endpoint PRs (#914, #918).

## Used by
- `bases/lif/mdr_restapi` (mounts `AuthMiddleware`)
