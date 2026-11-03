# `api_graphql` — Base

FastAPI + Strawberry GraphQL base that converts an OpenAPI schema (loaded from the MDR at startup) into a GraphQL schema at runtime. The resulting GraphQL types, filters, enums, and root queries are generated dynamically from the OpenAPI JSON — there are no hand-written `.graphql` files for the data model.

## Endpoints
- `POST /graphql` — Strawberry-managed GraphQL endpoint (queries + mutations)
- `GET /graphql` (GraphiQL UI when not authed-and-running-in-prod)

## Auth
API-key authentication via `lif.auth.AuthMiddleware` with `api_key_strategy` (`add_api_key_auth` in `core.py`). Configured by `GRAPHQL_AUTH__API_KEYS` env var (`key1:client1,key2:client2`). When unset, auth is disabled — fine for local dev, never for deployed envs.

## Error contract

A non-200 from the Query Planner is reported as a GraphQL `errors` entry with `data` null for
the queried field — **not** as an empty result set. Callers must therefore treat an empty list
as "this learner has no data" and read `errors` to detect a backend failure; before #1264 the
two were indistinguishable, so a 408 timeout looked like a successful empty response.

The message carries only the status (`Query failed: 408`, `Mutation failed: 500`). The Query
Planner's error body can contain backend internals, so it is never relayed to the caller (#1291
for queries, #1309 for the update mutation). The server log records only its length: a FastAPI
422 body echoes the request's filter, learner identifier included (#1351).

GraphQL errors are logged with their path, exception type and stack, but not their message or
the query document, both of which can hold learner data (#1351).

## Composes
- `auth` — `AuthMiddleware` + `api_key_strategy`
- `lif_schema_config` — env-driven config
- `logging` — logger setup
- `mdr_client` — fetches OpenAPI schema at startup
- `openapi_to_graphql` — the actual OpenAPI → GraphQL generator

## Deployed as
`projects/lif_graphql_api/`
