# `auth_utils` — Component

Shared helpers for the LIF auth bricks. Every function takes its inputs as arguments. Nothing in this brick reads the environment, so each consuming brick keeps its own secrets, allowlists, and claim policy (#548).

## Public surface

`lif.auth_utils` (no `jwt` import, safe for any service):

- `API_KEY_HEADER`: the `X-API-Key` header name.
- `DEFAULT_PUBLIC_PATHS` / `DEFAULT_PUBLIC_PATH_PREFIXES`: the default unauthenticated paths.
- `is_public_path(path, exact, prefixes)`: true if `path` is in `exact` or starts with one of `prefixes`.
- `extract_bearer_token(request)`: returns the token from `Authorization: Bearer <token>`, else `None`. The `Bearer` scheme matches case-insensitively.

`lif.auth_utils.hs256` (needs `pyjwt`; import it explicitly):

- `encode_hs256(claims, secret, expires_delta)`: signs a copy of `claims` with `exp` set.
- `decode_hs256(token, secret)`: verifies the token. An expired or invalid token raises a 401 `HTTPException` with `WWW-Authenticate: Bearer`.

## Why `hs256` is a separate module

GraphQL packages this brick through `api_key_auth` but does not ship `pyjwt`. Because `lif/auth_utils/__init__.py` never imports `hs256`, importing `lif.auth_utils` never loads `jwt`. `test_jwt_free_imports_do_not_load_pyjwt` enforces this.

Because of this, `poly check` reports "Cannot locate jwt in lif_graphql_api". That warning is expected and is not a runtime problem.

The brick reads no environment for the same reason `api_token_auth` was split out of `auth` in #1191: a shared helper must not force a service to configure secrets it never uses.

## Used by
- `components/lif/auth`: HS256 (Advisor)
- `components/lif/mdr_auth`: HS256, bearer extraction, header constant, public paths (MDR)
- `components/lif/cognito_auth`: bearer extraction, public-path defaults
- `components/lif/api_key_auth`: header constant, public paths
- `bases/lif/learner_data_export_api`: public paths in `CompositeAuthMiddleware`
