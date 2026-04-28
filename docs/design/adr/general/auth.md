# ADR 0001: API and User Auth

Date: 2025-10-31

## Status

Proposed

## Context

The LIF APIs and apps have a variety of auth flows that should be unified. This ADR highlights the current state and a plan for unification.

Current focus is on authentication. *Authorization* is an important function of a secure framework and needs to be designed / implemented as well. For now, the only things that hint at authorization are the different service keys in the MDR API.

Current state of the APIs and Apps are as follows.

### Advisor API:

Requires the caller to pass in a valid JWT access token. The environment variable `SECRET_KEY` is used as the JWT secret.

Each endpoint function requires a 'depends' call to verify the authentication.

### Advisor User:

Requires a `username` and `password`, and emits a JWT access token and a JWT refresh token.

The user base is hard coded with cleartext passwords (meant for PoC / demo purposes).

Uses an in-memory, per process, Python construct for tracking available refresh tokens.

### MDR API:

Requires the caller to pass in a valid JWT access token or pass in an API key via the `X-API-Key` header and confirms it matches one of the following three environment variables. The API key is checked before the JWT access token is reviewed.
- `MDR__AUTH__SERVICE_API_KEY__GRAPHQL`
- `MDR__AUTH__SERVICE_API_KEY__SEMANTIC_SEARCH`
- `MDR__AUTH__SERVICE_API_KEY__TRANSLATOR`

FastAPI Middleware is used to protect all endpoints by default. There are endpoint allowlists ( `MDR__AUTH__PUBLIC_ALLOWLIST_EXACT` and `MDR__AUTH__PUBLIC_ALLOWLIST_STARTS_WITH` ) to bypass authentication for endpoints such as `login`, `health check`, and `openAPI`.

The `MDR__AUTH__METHODS_TO_REQUIRE_AUTH` environment variable controls which HTTP methods will be protected by the authentication checks.

The environment variable `MDR__AUTH__JWT_SECRET_KEY` is used as the JWT secret.

### MDR User:

Requires a `username` and `password`, and emits a JWT access token and a JWT refresh token.

The user base is hard coded with hashed passwords (meant for PoC / demo purposes).

Uses an in-memory, per process, Python construct for tracking available refresh tokens.

### LIF API (GraphQL):

No authentication

### Example Data Source API:

Requires the caller to pass in the API key via the `x-key` header and confirms it matches the `API_TOKEN` environment variable.

## Decision

Unify all auth logic into a `component` for reuse across services, including:
- Environment variables for the JWT secret and TTLs
- User base
- Hashed passwords
- Auth audit trail (successful and failed logins)

All external APIs will authenticate with a service specific token, passed in via the `X-API-Key` header. This token will be stable until manually rotated.

Each LIF service calling an secured LIF API will use a separate token to allow future authorization flows.

Internal APIs are not in scope for this ADR, and will remain open for now. It is the responsibility of the hosting system admin to ensure these internal APIs are not exposed to the external web.

All user sessions will be managed by a JWT Bearer token and support automatic token refresh.

User access will be SSO, so once a user is logged into one of the frontend apps, they can access a different frontend app with the same Bearer token.

## Alternatives

- Continue to have siloed auth implementations. Rejected due to maintenance efforts and security concerns in bespoke auth implementations.

## Consequences

As alignment is realized, there will be some churn of environment variables for the services and possibly the apps which will take Engineer time.

There will be a 'one stop shop' in the polylith framework for LIF auth that `bases` can leverage to secure user/service interactions.

It will prepare the LIF ecosystem for additional auth flows to be introduced (Adopter specific / AWS Cognito / etc)

## References

*Advisor API auth:*

- https://github.com/LIF-Initiative/lif-main/blob/main/bases/lif/advisor_restapi/core.py

*Advisor App auth:*

- https://github.com/LIF-Initiative/lif-main/blob/main/frontends/lif_advisor_app/src/components/LoginPanel.tsx
- https://github.com/LIF-Initiative/lif-main/blob/main/frontends/lif_advisor_app/src/utils/axios.ts
- https://github.com/LIF-Initiative/lif-main/blob/main/frontends/lif_advisor_app/src/App.tsx

*Example Data Source API auth:*

- https://github.com/LIF-Initiative/lif-main/blob/main/bases/lif/example_data_source_rest_api/core.py

*MDR API auth:*

- https://github.com/LIF-Initiative/lif-metadata-repository/blob/main/service/app/main.py
- https://github.com/LIF-Initiative/lif-metadata-repository/blob/main/service/app/auth/core.py

*MDR App auth:*

- https://github.com/LIF-Initiative/lif-metadata-repository/blob/main/mdr-frontend/src/services/authService.ts
- https://github.com/LIF-Initiative/lif-metadata-repository/blob/main/mdr-frontend/src/services/api.ts
