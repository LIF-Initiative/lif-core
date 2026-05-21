# `api_graphql` — Base

FastAPI + Strawberry GraphQL base that converts an OpenAPI schema (loaded from the MDR at startup) into a GraphQL schema at runtime. The resulting GraphQL types, filters, enums, and root queries are generated dynamically from the OpenAPI JSON — there are no hand-written `.graphql` files for the data model.

## Endpoints
- `POST /graphql` — Strawberry-managed GraphQL endpoint (queries + mutations)
- `GET /graphql` (GraphiQL UI when not authed-and-running-in-prod)

## Auth
API-key authentication via `ApiKeyAuthMiddleware`. Configured by `GRAPHQL_AUTH__API_KEYS` env var (`key1:client1,key2:client2`). When unset, auth is disabled — fine for local dev, never for deployed envs.

## Composes
- `api_key_auth` — middleware
- `lif_schema_config` — env-driven config
- `logging` — logger setup
- `mdr_client` — fetches OpenAPI schema at startup
- `openapi_to_graphql` — the actual OpenAPI → GraphQL generator

## Deployed as
`projects/lif_graphql_api/`
