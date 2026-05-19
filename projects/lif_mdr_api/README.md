# LIF Metadata Repository (MDR) API

The **Metadata Repository (MDR)** is LIF's control-plane service. It holds the LIF data model (Base LIF + per-organization models), transformation definitions, value sets, and — since #883 — per-tenant routing configuration. Most other LIF services load their schema and transformation rules from here at startup.

Composed from `bases/lif/mdr_restapi/` + the `mdr_*` components. See [`../../bases/lif/mdr_restapi/README.md`](../../bases/lif/mdr_restapi/README.md) for the endpoint-group map and [`../../docs/design/cross-cutting/self-serve-tenant-auth.md`](../../docs/design/cross-cutting/self-serve-tenant-auth.md) for the multi-tenant story.

## Components

- **Database:** Postgres, deployed separately via [`../lif_mdr_database/`](../lif_mdr_database/). Schema is managed by Flyway migrations (V1.1, V1.2, V1.3 tenant cutover, V1.4 `clone_lif_schema`).
- **Frontend:** React/TypeScript UI lives at [`../../frontends/mdr-frontend/`](../../frontends/mdr-frontend/), deployed to S3+CloudFront via `scripts/release-demo-frontend.sh`.

## Building

```bash
# Wheel build (for distribution / debugging)
cd projects/lif_mdr_api
bash build.sh

# Docker image — uses Dockerfile2 (the canonical pattern; legacy Dockerfile retained)
bash build-docker.sh
```

`Dockerfile2` is the path used by CI and reference deployments — it does a two-stage build with `uv sync` from this project's `pyproject.toml`. Any new runtime dependency must be added **to this project's `pyproject.toml`, not just the monorepo root** (see [`../../docs/operations/guides/adding-a-new-microservice.md`](../../docs/operations/guides/adding-a-new-microservice.md) for the rationale).

## Configuration

All settings come from environment variables, parsed by `Settings` in `components/lif/mdr_utils/config.py`. Key env vars:

| Env var | Purpose |
|---|---|
| `POSTGRESQL_*` | Database connection |
| `MDR__AUTH__JWT_SECRET_KEY` | Signs HS256 access/refresh JWTs + workspace cookies + invite tokens |
| `MDR__AUTH__SERVICE_API_KEY__*` | One key per internal service caller (graphql, semantic_search, translator, post_confirm, learner_data_export) |
| `MDR__AUTH__COGNITO_*` | User pool id, region, SPA client id; empty user pool disables Cognito |
| `MDR__TENANT_ROUTING__ENABLED` | Flip to `true` after the tenant_lif_team cutover (#883 Phase 2 PR 3) |
| `MDR__TENANT_ROUTING__SERVICE_SCHEMA` | Fallback schema for service principals + group-less users |
| `MDR__COOKIE__SECURE` | Set `false` for local HTTP dev; defaults to `true` for HTTPS envs |
| `MDR__INVITE__TOKEN_MAX_AGE_SECONDS` | Invite token TTL (default 7 days) |

For local development, copy `.env.example` (if present) or seed the values inline via docker-compose.

## Running locally (Docker Compose)

The MDR API + database are wired into [`../../deployments/advisor-demo-docker/docker-compose.yml`](../../deployments/advisor-demo-docker/docker-compose.yml). From repo root:

```bash
cd deployments/advisor-demo-docker
docker compose up --build -d lif-mdr-database lif-mdr-api lif-mdr-app
```

Once up:
- API + Swagger: http://localhost:8012/docs
- Frontend: http://localhost:5173

## Testing

Component-level tests live under `test/components/lif/mdr_services/` and `test/components/lif/mdr_auth/`. Endpoint tests are at `test/bases/lif/mdr_restapi/`. Run from repo root:

```bash
uv run pytest test/components/lif/mdr_services/ test/components/lif/mdr_auth/ test/bases/lif/mdr_restapi/
```

Postgres-backed tests for the `clone_lif_schema` SQL function require a running database — see `test/.../test_clone_lif_schema_sql.py` for setup notes.
