# `auth` — Component

The one LIF auth brick ([ADR 0007](../../../docs/design/adr/general/0007-single-auth-brick-with-provider-adapters.md)). Identity providers are **strategies** that one middleware runs in order. A base composes the middleware with the strategies it needs instead of carrying its own auth.

## Public surface

`lif.auth` re-exports the modules that don't import `jwt`:

| Module | Contents |
|---|---|
| `lif.auth.middleware` | `AuthMiddleware(strategies, public_paths=None, public_prefixes=None, methods=None, challenge="Bearer")` |
| `lif.auth.principal` | `Principal(id, method, claims)`, `Strategy`, `AuthError` (an `HTTPException` 401) |
| `lif.auth.api_key` | `ApiKeyConfig.from_environment(prefix, header="X-API-Key")`, `api_key_strategy(config)` |
| `lif.auth.request` | `API_KEY_HEADER`, `DEFAULT_PUBLIC_PATHS` / `DEFAULT_PUBLIC_PATH_PREFIXES`, `is_public_path`, `extract_bearer_token` |
| `lif.auth.config` | `require_env(name)`, `resolve_secret(value, name)`: fail fast, naming the variable |

Import these explicitly:

| Module | Contents | Why it isn't re-exported |
|---|---|---|
| `lif.auth.jwt` | `JwtConfig.from_environment(secret_var)`, `mint_access`, `mint_refresh`, `verify(config, token, expected_type=None)`, `jwt_strategy`, `encode_hs256` / `decode_hs256` | imports `jwt` |
| `lif.auth.cognito` | `CognitoAuthConfig`, `decode_cognito_jwt`, `authenticate_request`, `cognito_strategy`, `require_crypto` | imports `jwt` |

## The contract

- **A strategy returns one of three things:**
  - a `Principal` when it authenticated the caller;
  - `None` when the request doesn't carry its kind of credential, so the next strategy runs;
  - or it raises `AuthError` when the credential is its kind but invalid, which rejects the request with that message.
- **`AuthMiddleware` uses the first `Principal`.** It sets `request.state.principal` (the id), `request.state.auth_method`, and `request.state.claims`. No match, or an `AuthError`, returns a JSON 401 with `WWW-Authenticate`.
- **`cognito_strategy` returns `None` for an invalid token rather than raising,** because the bearer token may belong to another strategy in the same middleware.

```python
from lif.auth import AuthMiddleware, ApiKeyConfig, api_key_strategy

app.add_middleware(AuthMiddleware, strategies=[api_key_strategy(ApiKeyConfig.from_environment("GRAPHQL_AUTH"))])
```

## Secrets

Signing secrets are read only through `JwtConfig.from_environment` / `resolve_secret`. A secret that is unset, blank, or a placeholder published in this repo (`changeme`, `changeme1`–`6`, `change4`, `replace`, ...) raises at startup, naming the variable.

## GraphQL and `pyjwt`

GraphQL packages this brick but does not ship `pyjwt`. `test_jwt_free_imports_do_not_load_pyjwt` checks that importing `lif.auth` and the `jwt`-free modules never loads `jwt`. Because of this, `poly check` reports "Cannot locate jwt in lif_graphql_api"; that warning is expected.

## Used by

- `components/lif/mdr_auth`: `config`, `jwt`, `cognito`, `request`
- `bases/lif/advisor_restapi`: `AuthMiddleware` + `jwt_strategy`; mints with `JwtConfig.from_environment("SECRET_KEY")`
- `bases/lif/example_data_source_rest_api`: `AuthMiddleware` + `api_key_strategy` (`x-key` vs `API_TOKEN`)
- `bases/lif/api_graphql`: `AuthMiddleware` + `api_key_strategy` (`GRAPHQL_AUTH__*`; off when no keys)
- `bases/lif/learner_data_export_api`: `AuthMiddleware` + `api_key_strategy`, or `[developer-key stub, cognito_strategy]` in composite mode
