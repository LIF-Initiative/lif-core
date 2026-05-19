# `query_planner_restapi` — Base

FastAPI base for the LIF Query Planner: takes a `LIFQuery` and decides *how* to fulfill it — which data sources to hit, which fragments come from cache vs. fresh orchestration, how to route the result through any required translations. The GraphQL API delegates to the Query Planner; the planner in turn calls the Query Cache and Orchestrator.

## Endpoints
- `POST /query`              — synchronous query; returns `List[LIFRecord]`
- `POST /query_async`        — async variant; returns either records (cache hit) or a `LIFQueryStatusResponse` to poll
- `GET  /query/{query_id}/status` — poll status of an in-flight async query
- `POST /update`             — apply a `LIFUpdate`
- `POST /orchestration/results` — callback endpoint for the Orchestrator to report back when an async job finishes
- `GET  /`                   — sanity ping

Async polling is bounded by `MIN_POLLING_DELAY_SECONDS` (1) and `MAX_POLLING_DELAY_SECONDS` (16) with `MAX_QUERY_TIMEOUT_SECONDS=60` per the constants in `core.py`.

## Configuration
The planner reads YAML at startup that describes available information sources (the per-org `information_sources_config.yml` files under `deployments/*/`). One planner instance runs per org in the reference deployment.

## Composes
- `datatypes` — `LIFQuery`, `LIFRecord`, `LIFUpdate`, planner-side types
- `exceptions`
- `logging`
- `query_planner_service` — `LIFQueryPlannerService` (the actual planning logic)

## Deployed as
`projects/lif_query_planner_api/`
