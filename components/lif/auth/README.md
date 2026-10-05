# `auth` — Component

Lightweight HS256 JWT auth used by the Advisor base. Not the same as [`mdr_auth`](../mdr_auth/): this one is older and simpler, with no Cognito or middleware-managed tenant routing. Demo-grade.

## Public surface

```python
from lif.auth.core import (
    create_access_token, create_refresh_token, decode_jwt, get_current_user,
)
```

- `create_access_token` / `create_refresh_token` mint short-lived access tokens (30 min) and longer-lived refresh tokens (7 days).
- `decode_jwt` verifies a token. On failure it raises a 401 `HTTPException` with `WWW-Authenticate: Bearer`.
- `get_current_user` is the FastAPI `Depends(...)` callable that extracts the authenticated username from a bearer token.

Signing and verification are delegated to [`auth_utils.hs256`](../auth_utils/). This brick keeps the secret and the expiry policy.

## Configuration

`SECRET_KEY` is required **at import**, with no fallback (#1191). The static `API_TOKEN` check now lives in [`api_token_auth`](../api_token_auth/), so services that only need that check don't have to set a signing key.

## Used by
- `bases/lif/advisor_restapi`: login and per-endpoint user resolution

New services should default to `mdr_auth` instead unless they specifically don't want Cognito support.
