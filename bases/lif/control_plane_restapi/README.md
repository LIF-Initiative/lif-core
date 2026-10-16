# `control_plane_restapi` — Base

FastAPI base for the LIF **control plane** (EPIC #1041, ADR 0002 and ADR 0006): the service that will own developer keys, and later identity and admin, outside MDR.

So far it's the service and its own database, without the key endpoints (#1182). The developer-key table and endpoints wait on #1190.

## Endpoints

| Path | Auth | What it does |
|---|---|---|
| `/health-check` | public | `200 {"status": "ok"}` when the control plane's database answers `SELECT 1`, otherwise `503` |
| `/docs`, `/openapi.json` | public | FastAPI docs |

## Auth
Cognito JWTs only, through `CognitoAuthMiddleware` from `cognito_auth` (configured with `CONTROL_PLANE_AUTH__USER_POOL_ID` / `__REGION` / `__CLIENT_ID`). **It fails closed:** with no user pool configured, every non-public path returns `401`, and the service never tries to verify a token against an empty pool.

## Config
- `CONTROL_PLANE__DATABASE_URL` (required): an async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@host:5432/db`. Startup fails, naming the variable, if it's missing (#1179).
- `CONTROL_PLANE_AUTH__*`: see Auth.

Nothing from the MDR domain is imported or configured.

## Composes
- `cognito_auth` — Cognito JWT verification and middleware
- `logging` — `get_logger`

## Deployed as
`projects/lif_control_plane_api/` (API, port 8014) + `projects/lif_control_plane_database/` (its migrations). Local compose only for now; the dev/demo deploy is the AWS half of #1182.
