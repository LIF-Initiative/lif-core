# cognito_auth

Reusable **Cognito JWT** authentication — a single-purpose decoration brick
(ADR 0004). It validates that a request carries a valid Cognito access/ID token
from the configured user pool and exposes the claims; it carries **no** MDR,
tenant, or LDE concerns.

## Why a separate brick

`mdr_auth` bundles Cognito validation with MDR tenant routing and service keys.
`cognito_auth` extracts just the Cognito piece, configured per-service, so any
service (LDE, others) can compose it without pulling in MDR. This is the pattern
in ADR 0004: bare capability in a component, composed at the edges.

## Public surface

- `CognitoAuthConfig` — `from_environment(prefix="COGNITO_AUTH")`; reads
  `{PREFIX}__USER_POOL_ID` / `__REGION` / `__CLIENT_ID`. `is_enabled` is false
  when no pool is set, so a bare deployment runs without Cognito.
- `decode_cognito_jwt(token, config)` — verify + decode (raises on invalid).
- `authenticate_request(request, config) -> claims | None` — the composable
  **strategy**: returns claims for a valid Bearer JWT, else `None` (never raises),
  so a composite can fall through to another strategy.
- `CognitoAuthMiddleware` — optional standalone Cognito-only middleware.

## Composition (the LDE case, #1034)

LDE stays **bare on `api_key_auth`** by default. When developer keys + Cognito are
enabled, the LDE base composes a *composite* inbound middleware that accepts a
**signed developer key OR a Cognito JWT** — calling `authenticate_request` here as
the JWT strategy and the developer-key validator (signed-token offline verify,
#1033/#1038, ADR 0002) as the other. The composite lives at the base (composition
is a base concern); this brick just provides the Cognito strategy.
