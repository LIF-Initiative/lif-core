# `query_planner_restapi` — Base

FastAPI base for the LIF Query Planner: takes a `LIFQuery` and decides *how* to fulfill it — which data sources to hit, which fragments come from cache vs. fresh orchestration, how to route the result through any required translations. The GraphQL API delegates to the Query Planner; the planner in turn calls the Query Cache and Orchestrator.

## Endpoints
- `POST /query`              — synchronous query; returns `List[LIFRecord]`
- `POST /query_async`        — async variant; returns either records (cache hit) or a `LIFQueryStatusResponse` to poll
- `GET  /query/{query_id}/status` — poll status of an in-flight async query
- `POST /update`             — apply a `LIFUpdate`
- `POST /orchestration/results` — callback endpoint for the Orchestrator to report back when an async job finishes
- `GET  /`                   — sanity ping

The sync `/query` polling loop backs off between `MIN_POLLING_DELAY_SECONDS` (1) and `MAX_POLLING_DELAY_SECONDS` (16) seconds, and returns `408` once `LIF_QUERY_TIMEOUT_SECONDS` is exceeded.

## Configuration
The planner reads YAML at startup that describes available information sources (the per-org `information_sources_config.yml` files under `deployments/*/`). One planner instance runs per org in the reference deployment.

| Variable | Code default | Purpose |
|---|---|---|
| `LIF_QUERY_TIMEOUT_SECONDS` | `300` | Whole-query budget for the synchronous `/query` polling loop; the endpoint returns `408` once it is exceeded |
| `LIF_SERVICE_REQUEST_TIMEOUT_SECONDS` | `10` | Per-request timeout for the planner's own HTTP calls to the Query Cache and Orchestrator, independent of the budget above |

**Deployed config sets `LIF_QUERY_TIMEOUT_SECONDS` to `120`, not the code default.** The planner has no load balancer of its own, but every externally reachable caller of `/query` sits behind the shared ALB, whose idle timeout is 150s (`LoadBalancerIdleTimeoutSeconds` in `cloudformation/service-common.yml`). Above 150 the planner never gets to return its `408` — the ALB cuts the connection first with a 504, which surfaces in the browser as a CORS error (#1050). Raising the budget past 150 means raising the ALB idle timeout with it.

A **malformed** value for either timeout — `"120s"`, or `0` — stops the service at startup with a message naming the variable, per the convention decided in #1179. Unset or empty falls back to the code default.

## Composes
- `datatypes` — `LIFQuery`, `LIFRecord`, `LIFUpdate`, planner-side types
- `exceptions`
- `logging`
- `query_planner_service` — `LIFQueryPlannerService` (the actual planning logic)

## Deployed as
`projects/lif_query_planner_api/`
