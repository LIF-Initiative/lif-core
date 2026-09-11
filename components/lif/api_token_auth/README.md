# api_token_auth

Static shared-secret token check.

## Purpose

Verifies a caller-supplied token against the `API_TOKEN` environment variable.
This is a plain shared secret — no signing, no claims, no expiry. For JWT minting
and verification see [`auth`](../auth/README.md); for API-key middleware see
[`api_key_auth`](../api_key_auth/README.md); for Cognito see
[`cognito_auth`](../cognito_auth/README.md).

Split out of `auth` in #1191 so that a service needing only this check is not
forced to configure a JWT signing key it never uses. `auth` requires `SECRET_KEY`
at import; this brick does not.

## Public surface

- `verify_token(token: str) -> None` — raises `HTTPException(401)` when
  `API_TOKEN` is unset or the supplied token does not match.

## Configuration

| variable | required | purpose |
|---|---|---|
| `API_TOKEN` | yes | the expected shared secret; an unset value rejects every request |

## Consumers

- `bases/lif/example_data_source_rest_api`
