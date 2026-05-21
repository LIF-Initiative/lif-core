# `auth` — Component

Lightweight HS256 JWT auth used by the Advisor and Example Data Source bases. Not the same as [`mdr_auth`](../mdr_auth/) — this one is older and simpler, with no Cognito or middleware-managed tenant routing. Demo-grade.

## Public surface

```python
from lif.auth.core import (
    create_access_token, create_refresh_token, decode_jwt,
    verify_token, get_current_user,
)
```

`create_access_token` / `create_refresh_token` mint short-lived access tokens and longer-lived refresh tokens. `verify_token` is a sync validator suitable for use as a FastAPI dependency. `get_current_user` is the FastAPI `Depends(...)` callable that extracts the authenticated username from a bearer token.

## Used by
- `bases/lif/advisor_restapi` — login + per-endpoint user resolution
- `bases/lif/example_data_source_rest_api` — `verify_token` behind `x-key` header auth

New services should default to `mdr_auth` instead unless they specifically don't want Cognito support.
