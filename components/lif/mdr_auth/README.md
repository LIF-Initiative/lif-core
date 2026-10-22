# `mdr_auth` — Component

Authentication for the LIF Metadata Repository API, composed from [`auth`](../auth/) (ADR 0007). `add_mdr_auth(app)` mounts `lif.auth`'s `AuthMiddleware` with three strategies, tried in this order:

- **Service API-keys** — internal services (GraphQL, Translator, Semantic Search, Post-Confirmation Lambda, Learner Data Export) authenticate with `X-API-Key`; the principal is `service:<name>`. An unknown key is a 401, even if a Bearer token is also sent.
- **Cognito JWT** — end users from the self-serve flow, validated against the user pool's JWKS. MDR's adapter (`_cognito_strategy`) takes tokens with a `kid` header; the principal is the email, falling back to `sub`.
- **Legacy HS256 JWT** — pre-Cognito callers (demo accounts, etc.), `lif.auth.jwt.jwt_strategy(JWT_CONFIG, expected_type="access")`.

`TenantMiddleware` then runs after authentication. It sets `request.state.cognito_groups` / `cognito_sub` and resolves `request.state.tenant_schema` per request based on the caller's `cognito:groups` claim and an optional workspace-selection cookie — see [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../../docs/design/cross-cutting/self-serve-tenant-auth.md).

## Public surface

```python
from lif.mdr_auth import (
    add_mdr_auth,      # wires AuthMiddleware + TenantMiddleware in the right order
    JWT_CONFIG,        # lif.auth.jwt.JwtConfig from MDR settings; mint with lif.auth.jwt.mint_access/mint_refresh
    TenantMiddleware,
)
```

HS256 signing/verification, the middleware, the API-key strategy, bearer extraction, the `X-API-Key` header name, the public-path check, secret resolution, and Cognito JWT validation all come from [`auth`](../auth/) (`lif.auth.jwt`, `lif.auth.request`, `lif.auth.config`, `lif.auth.cognito`); `core.py` builds its `CognitoAuthConfig` (`COGNITO_CONFIG`) from MDR settings. If `MDR__AUTH__COGNITO_USER_POOL_ID` is set but `MDR__AUTH__COGNITO_SPA_CLIENT_ID` is empty, the module fails at import rather than accepting tokens from any app client in the pool.

Phase 3 of issue #884 adds `workspace_cookie.py` (HMAC-signed workspace selection cookie) and `invite_token.py` (signed invite tokens for tenant sharing). Those land alongside the corresponding endpoint PRs (#914, #918).

## Used by
- `bases/lif/mdr_restapi` (calls `add_mdr_auth`; `/login` and `/refresh-token` mint and verify with `JWT_CONFIG`)
