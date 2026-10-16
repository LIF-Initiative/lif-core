# ADR 0007: One auth brick, with identity providers as strategies and one composable middleware

Date: 2026-10-06

## Status
Accepted

## Context

[ADR 0001](auth.md) decided to unify LIF auth into reusable components. What we actually have is five parallel auth bricks plus a shared-helper brick. Each service base wires inbound auth differently:

| Service | Inbound auth today |
|---|---|
| Advisor API | Per-route `Depends(get_current_user)` from `auth`. HS256 tokens, signed with `SECRET_KEY`. |
| Example Data Source API | Router dependency checking the `x-key` header against `API_TOKEN` (`api_token_auth`). |
| GraphQL API | `ApiKeyAuthMiddleware` from `api_key_auth`. |
| Learner Data Export API | `api_key_auth` by default. In composite mode, which AWS runs, its own `CompositeAuthMiddleware` tries a developer-key stub and then `cognito_auth`. |
| MDR API | `mdr_auth.AuthMiddleware`: service API key → Cognito → HS256, then tenant resolution. |

The code is duplicated across these stacks. Cognito JWT validation is implemented twice (`cognito_auth` and `mdr_auth`), and so is HS256 signing and decoding (`auth` and `mdr_auth`). Bearer parsing, the `X-API-Key` header name and public-path matching are re-implemented per brick. Each base also sets different `request.state` fields (`api_client`, `principal` as a string or as a claims dict, `cognito_sub`).

Secret handling is also inconsistent:
- `auth` fails at import when `SECRET_KEY` is missing (#1191).
- MDR's JWT secret silently falls back to the public value `"changeme4"` (`mdr_utils/config.py`). That secret also signs the workspace cookie and invite tokens.
- MDR's five service API keys fall back to `changeme1`–`6`, so a deployment missing one accepts a well-known key.

The settings class that holds these values (`mdr_utils`) is also loaded by the Learner Data Export API, which sets none of them. So requiring them in the settings class itself would break that service.

Two constraints shape the design:
- **GraphQL packages API-key auth but does not ship `pyjwt`.** Anything it imports must not import `jwt`.
- **#1041 ([ADR 0002](0002-lif-control-plane-vs-mdr-host.md)) is moving developer keys, and possibly Cognito identity, out of MDR.** #1180 extracts a `developer_keys` brick. That code relies on the `request.state` fields MDR's middleware sets, and both efforts edit `bases/lif/mdr_restapi/core.py`.

## Decision

**1. One brick: `components/lif/auth`.** It replaces `api_key_auth`, `api_token_auth`, `cognito_auth` and the Advisor-only `lif.auth.core`, and the HS256 and Cognito code in `mdr_auth`. It has these modules:

| Module | Contents | Imports `jwt`? |
|---|---|---|
| `config` | `require_env(name)` and `resolve_secret(value, name)`: fail fast and loud, naming the variable (#1179) | no |
| `request` | `API_KEY_HEADER`, default public paths, `is_public_path`, `extract_bearer_token` | no |
| `principal` | `Principal(id, method, claims)` and `AuthError(detail, status=401, challenge)` | no |
| `middleware` | `AuthMiddleware(strategies, public_paths, public_prefixes, methods)`: the only inbound auth middleware | no |
| `api_key` | `ApiKeyConfig.from_environment(prefix, header=...)` and `api_key_strategy`. A single static token, like the Example Data Source's `x-key`, is a one-key config. | no |
| `jwt` | `JwtConfig`, `mint_access` / `mint_refresh`, `verify`, `jwt_strategy(config, expected_type=None)` | yes |
| `cognito` | `CognitoAuthConfig`, JWKS/RS256 decode, `cognito_strategy` | yes |

`lif/auth/__init__.py` re-exports only the modules that don't import `jwt`, and it must not import any module with side effects at import time. A test that imports the package in a separate process enforces both rules.

**2. Identity providers are strategies, not parallel stacks.** A strategy is `Callable[[Request], Principal | None]`:
- **`None`** means "not my kind of credential, try the next strategy".
- **Raising `AuthError`** means "my kind of credential, but invalid: reject". This keeps specific messages such as "Token has expired".

`AuthMiddleware` runs the strategies in order and the first `Principal` wins. It sets `request.state.principal` (a string id), `request.state.auth_method`, and `request.state.claims`. An `AuthError`, or no match, returns a 401 JSON body with `WWW-Authenticate`.

**3. One JWT implementation with one error contract.** `lif.auth.jwt` is the only place that signs and verifies tokens, and `verify` raises `AuthError`. Service-specific claim rules are parameters, not forks. For example, MDR requires `type == "access"`, and MDR refresh tokens carry `jti`.

**4. One secret source and no silent defaults.**
- Signing secrets are read only through `JwtConfig.from_environment` and `resolve_secret`. A secret that is unset, blank, or a known placeholder (`changeme*`) raises at startup, naming the variable.
- Existing env var names stay as they are: `SECRET_KEY` for the Advisor, `MDR__AUTH__JWT_SECRET_KEY` for MDR. One mechanism doesn't need new names, and renaming would mean SSM and CloudFormation changes in every environment.
- MDR service API keys have no defaults. An unset key is simply not accepted, and MDR logs a startup warning naming it.
- These checks run in the auth code of the service that needs the value, never in a settings class other services share.

**5. Bases compose; they don't implement.** Every base adds `lif.auth.middleware.AuthMiddleware` with its own list of strategies, and nothing else:

| Service | Strategies |
|---|---|
| Example Data Source | `[api_key (x-key)]` |
| GraphQL | `[api_key]` |
| Learner Data Export | `[api_key]`, or `[developer_key, cognito]` in composite mode |
| Advisor | `[jwt]` |
| MDR | `[service api_key, cognito, jwt(expected_type="access")]` |

Service-specific follow-on work runs as a separate step after auth. For MDR that's tenant resolution, `X-API-Tenant-Schema`, and the workspace cookie. `mdr_auth` keeps only that MDR-specific code.

**6. Sequencing.** The four non-MDR services move first, and the old bricks are deleted once nothing imports them. The MDR migration (decision 5, MDR row) does not start until #1180 lands, and it is re-planned against what #1180 actually ships.

The MDR step followed #1180 (`developer_keys`, which reads `request.state.cognito_sub`). `mdr_auth.add_mdr_auth` mounts `AuthMiddleware` with `[service api_key, cognito adapter, jwt(expected_type="access")]`, then `TenantMiddleware`. The Cognito adapter is MDR's own: it keeps the email principal, and it rejects an invalid token that has a `kid` with a specific message rather than handing it to the HS256 strategy.

## Alternatives

- **Keep the separate bricks and extract the duplicated helpers into a shared `auth_utils` brick.** Rejected: duplicate lines go, but each base still carries a different middleware and `request.state` shape, so every new service or provider means a new stack. The brick that owns shared auth would also be named "utils", while `auth`, the obvious name, stayed a confusing Advisor-only brick.
- **Rename secrets to one `{PREFIX}__JWT_SECRET_KEY` convention.** Rejected for now: one mechanism already gives one documented source, and renames need SSM and CloudFormation changes in dev and demo, with no security gain.
- **Fail at startup when any MDR service key is unset.** Rejected: deployments that don't run every caller, such as local compose without the post-confirm Lambda, would have to set keys they never use. Rejecting the unset key gives the same safety.
- **Do MDR now, in parallel with #1180.** Rejected: both change how MDR's middleware sets `request.state` and edit the same base file. Doing them without coordinating means conflicts, or a contract that #1180 then has to undo.

## Consequences

- Adding an identity provider means writing one strategy, not another middleware. A new service gets auth by listing strategies.
- Downstream code reads one `request.state` contract: `principal`, `auth_method`, `claims`. MDR keeps setting `cognito_groups`, `cognito_sub` and `tenant_schema` in its tenant step, so its endpoints don't change.
- Misconfigured secrets fail at deploy time, loudly, instead of running on a public value. That also exposes deployments that are already missing values. Known gaps found while writing this ADR, and their outcome:
  - The 1-org and 3-org advisor compose files set no `SECRET_KEY`. **Fixed:** they pass it through (plain `${SECRET_KEY}`, so data-layer-only runs still parse).
  - The demo compose calls MDR from the Learner Data Export API with the translator's key. **Fixed:** LDE has its own key.
  - The demo compose runs the Learner Data Export API unauthenticated. **Kept on purpose:** the MDR frontend's export playground calls it with an MDR bearer token, which `api_key` mode can't accept.
- **Visible behaviour changes:**
  - The Advisor answers a missing token with 401 instead of 403 (`HTTPBearer`'s default).
  - The Example Data Source fails at startup when `API_TOKEN` is unset, instead of rejecting every request.
  - The Learner Data Export API's composite mode starts honouring `LDE_AUTH__PUBLIC_PATHS*`.
  - MDR rejects an unknown `X-API-Key` with 401, instead of falling through to the Bearer token.
  - MDR answers a request with no credentials with `Missing or invalid credentials` instead of `Authentication required: …`.
- **Trade-off:** one brick is packaged by every service with inbound auth. A change to it rebuilds all of them, and the deploy-workflow path filters (#1171, `scripts/check_workflow_paths.py`) must keep covering it. In return there's one place to review auth changes.
- **Trade-off:** keeping the old env var names means the "one source" is a mechanism, not a naming convention. The per-service variable names have to be documented, in [`docs/operations/guides/auth-configuration.md`](../../../operations/guides/auth-configuration.md).
- **Risk:** while the migration is in progress, the old bricks sit beside `lif.auth`. Each must be deleted once its last consumer moves, or the duplication returns under new names.

## References

- Builds on [ADR 0001 — API and User Auth](auth.md); refines its "one stop shop" decision.
- [ADR 0002 — LIF control plane vs MDR host](0002-lif-control-plane-vs-mdr-host.md) and epic #1041; #1180 (`developer_keys` extraction) gates the MDR step.
- [ADR 0004 — Components are the unit of reuse](0004-components-are-the-unit-of-reuse.md): auth as composition at the edges.
- Issue #548 (auth consolidation); #1034 (`cognito_auth` and the LDE composite middleware); #1191 (`SECRET_KEY` fail-fast); #1179 (config fail-fast convention); #1093 (`pyjwt[crypto]` guard); #1171 (deploy path filters).
