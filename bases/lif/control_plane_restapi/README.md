# `control_plane_restapi` — Base

FastAPI base for the LIF **control plane** (EPIC #1041, ADR 0002, ADR 0006 and ADR 0008): the service that will own developer keys, and later identity and admin, outside MDR.

So far it's the service, its own database, and the developer-key endpoints (#1182). Keys are owned by the caller's Cognito `sub` and scoped to a workspace, which is the tenant schema name kept as an opaque string (ADR 0008).

## Endpoints

| Path | Auth | What it does |
|---|---|---|
| `/health-check` | public | `200 {"status": "ok"}` when the control plane's database answers `SELECT 1`, otherwise `503` |
| `/docs`, `/openapi.json` | public | FastAPI docs |
| `POST /api-keys/?workspace=W` | Cognito, member of `W` | Issues a key. Body `{"Label": "..."}`. Returns `201` with the raw key, the only time it's shown. |
| `GET /api-keys/?workspace=W` | Cognito, member of `W` | The caller's own keys in `W`, never the raw key |
| `DELETE /api-keys/{id}` | Cognito, owner of the key | Soft-revokes the key (`204`). Needs ownership only, so it works after the caller has left `W`. Someone else's key is a `404`. |

**Membership:** the caller belongs to `W` when one of their `cognito:groups` satisfies `tenant_schema_for_group(group) == W` (`lif.tenant_routing`), the rule MDR's `find_workspace` applies. Otherwise the request gets a `403`. `W` is compared whole and never built from a group. A missing or empty `workspace` is a `422`. A caller that isn't a Cognito user gets a `400`, which can't happen today, since Cognito is the only strategy.

## Auth
Cognito JWTs only, through `lif.auth`'s `AuthMiddleware` with `cognito_strategy` (configured with `CONTROL_PLANE_AUTH__USER_POOL_ID` / `__REGION` / `__CLIENT_ID`). **It fails closed:** if the user pool or the client ID isn't configured, the middleware has no strategies, so every non-public path returns `401`. The service never tries to verify a token against an empty pool, and never accepts one without checking its client ID (with no client ID, `decode_cognito_jwt` would accept a token from any app client in the pool).

## Config
- `CONTROL_PLANE__DATABASE_URL` (required): an async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@host:5432/db`. Startup fails, naming the variable, if it's missing (#1179).
- `CONTROL_PLANE_AUTH__*`: see Auth.

Nothing from the MDR domain is imported or configured.

## Composes
- `auth` — `AuthMiddleware` and the Cognito strategy (`lif.auth.cognito`)
- `developer_keys` — the workspace-scoped key store (`workspace_store`)
- `logging` — `get_logger`
- `tenant_routing` — `tenant_schema_for_group`, for the membership check

## Deployed as
`projects/lif_control_plane_api/` (API, port 8014) + `projects/lif_control_plane_database/` (its migrations). Local compose only for now; the dev/demo deploy is the AWS half of #1182.
