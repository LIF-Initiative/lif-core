# `query_cache_restapi` — Base

FastAPI base for the LIF Query Cache: caches MongoDB-backed LIF records so the GraphQL API doesn't re-orchestrate the same data on every request. One Query Cache instance runs per organization in the reference deployment (`query-cache-org1`, `-org2`, `-org3`).

## Endpoints
- `POST /query`  — read cached records for a `LIFQuery` filter
- `POST /update` — mutate a cached record via a `LIFUpdate` payload
- `POST /add`    — add a new `LIFRecord`
- `POST /save`   — bulk-save fragments
- `GET  /`       — sanity ping

## Composes
- `datatypes` — `LIFQuery`, `LIFRecord`, `LIFFragment`, `LIFUpdate` shapes
- `exceptions` — common LIF exception types
- `logging`
- `query_cache_service` — the actual cache logic (Mongo-backed)

## Deployed as
`projects/lif_query_cache_api/`
