# Timeouts

The timeout ladders on the retrieval and export paths, the outward-in rule they follow, and the constraints that must hold when any one value is changed.

Every value below was verified against `main` at `9b168c8` on 2026-09-22. When you change one, update this table in the same PR — a ladder that silently drifts is worse than no ladder, because it reads as authoritative.

## The rule: outward-in

**Each hop's timeout must be shorter than the hop outside it.** The outermost caller must be the last to give up, so a slow inner call surfaces as a clean error with a cause in the logs, instead of the outer layer cutting the connection on a request that is still in flight.

The rule was already written down in this repo before it was applied to the retrieval path — in the comment above `TRANSLATOR_CLIENT_TIMEOUT_SECONDS` (`cloudformation/lif-learner-data-export-api-taskdef-includes.yml`):

> The timeout hierarchy has to run outward-in — monitor (60s) > LDE (45s) > actual export — so a slow export surfaces as a clean 500 with a cause in the logs, instead of the monitor timing out first on a request that is still in flight.

When the rule is broken the failure is not merely late, it is *misattributed*: an ALB that gives up first returns a 504 that the browser reports as a CORS error (#1050), which sends the next person looking at CORS configuration rather than at a slow query.

## The retrieval ladder

Outward-in. "Deployed" is the value in the task definition; "code default" is what the service uses if the environment variable is absent.

| Hop | Setting | Deployed | Code default | Source |
|---|---|---|---|---|
| Client → ALB | `LoadBalancerIdleTimeoutSeconds` | **150** | 150 | `cloudformation/service-common.yml` (parameter default; no `*.params` override) |
| MCP → GraphQL | `SEMANTIC_SEARCH_SERVICE__GRAPHQL_TIMEOUT__READ` | 300 | — | `cloudformation/lif-semantic-search-taskdef-includes.yml` |
| GraphQL → QP | `LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS` | 300 | — | `cloudformation/lif-graphql-taskdef-includes.yml` |
| LDE → QP | `QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS` | **30** | 30 | `cloudformation/lif-learner-data-export-api-taskdef-includes.yml`; `components/lif/query_planner_client/core.py` |
| QP sync poll ceiling | `LIF_QUERY_TIMEOUT_SECONDS` | **120** | **300** | `cloudformation/lif-query-planner-taskdef-includes.yml`; `bases/lif/query_planner_restapi/core.py` |
| QP → Cache / Orchestrator (per request) | `LIF_SERVICE_REQUEST_TIMEOUT_SECONDS` | 10 | 10 | same two files |

**The two 300s in the middle do not currently bind, but not for the reason the numbers suggest.** Neither hop traverses the ALB: both use internal service DNS (`http://graphql-org1.lif.${EnvironmentName}.aws:8000/graphql` and `http://query-planner-${OrganizationName}.lif.${EnvironmentName}.aws:8002`), and of these services only GraphQL sits behind the load balancer at all (`UseLbForService` is `true` for graphql, advisor-api and learner-data-export-api; `false` for semantic-search and query-planner).

They do not fire because the *work* underneath them is bounded first: the Query Planner stops polling at 120s, so a 300s client timeout above it never elapses. That slack is safe only while the 120 holds — if the planner's ceiling ever reverted to its 300 code default (see below), these two 300s would go live at the same moment the ALB began cutting at 150. They are listed for that reason, not because they are inert.

`LIF_SERVICE_REQUEST_TIMEOUT_SECONDS` (10) bounds a single QP→Orchestrator or QP→Cache call, not the whole query, so it is not a rung on this ladder. Its basis is measured and recorded in [`lif-orchestrator.md`](../components/lif-orchestrator.md#performance-report) (#572).

## The binding constraint: QP poll ceiling < ALB idle timeout

**`LIF_QUERY_TIMEOUT_SECONDS` must stay below `LoadBalancerIdleTimeoutSeconds` (150).**

Above 150 the Query Planner never gets to return its clean 408: the ALB cuts the connection first with a 504, which surfaces in the browser as a CORS error (#1050). The deployed 120 leaves ~30s of headroom for the QP's own response and the caller's hop.

**This currently holds by coincidence, not by construction.** The deployed value is 120, but the code default is **300** (`DEFAULT_QUERY_TIMEOUT_SECONDS`). Drop the environment variable — a new environment, a task definition that forgets it, a local compose file — and the ceiling silently returns to 300, re-inverting the ladder with no error anywhere. Nothing enforces the relationship; only this note and the comments on both values stand between the constraint and someone undoing it.

The same shape appears on the export path: `TRANSLATOR_CLIENT_TIMEOUT_SECONDS` deploys 45 but defaults to **30** in code, so dropping that variable silently *shortens* the budget the 45 was chosen to provide (#1157).

## The export ladder

Outward-in, and the one place the rule was already stated:

| Hop | Setting | Deployed | Code default | Source |
|---|---|---|---|---|
| e2e monitor | `SIXTY_SECONDS` | 60 | — | `e2e/tests/mdr-export-playground.spec.ts` |
| LDE → Translator | `TRANSLATOR_CLIENT_TIMEOUT_SECONDS` | 45 | **30** | `cloudformation/lif-learner-data-export-api-taskdef-includes.yml`; `components/lif/translator_client/core.py` |

45s rather than 30 because a CLR/OB3 export evaluates 32 JSONata expressions over the full record (#1157). A value above 60 would invert the ladder against the monitor.

## Unresolved: LDE → Query Planner

`QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS` is **30**, while the planner itself polls to 120. By the outward-in rule that is an inversion — the caller gives up long before the service it called.

**It is not recorded whether that is deliberate.** The value arrived in `db680b2` (#906, "Add timeouts to QP and Translator clients"), which gave both clients the same round 30 in one commit. Its sibling was later argued up to 45 for a concrete, documented reason; this one was never revisited. So there is no decision here to respect — which is the point: nobody changing it can tell whether they are undoing one.

A short export budget may well be the right answer, exactly as the translator's 45 is. What is missing is the sentence saying so. Until someone writes it, treat this number as open rather than settled.

**The archaeology has already been done, on 2026-09-22, and came up empty — it does not need repeating.** `git log -S QUERY_PLANNER_CLIENT_TIMEOUT_SECONDS` returns exactly one commit (`db680b2`), whose message is just the issue title; #906 is a feature issue for learner data export that never discusses the number. Asked directly, the team did not have the history either. So this is not "undocumented pending someone remembering" — the reason is gone, and changing the value would need a fresh decision rather than a recovered one. It is recorded here as **found**, not resolved.

One consequence is not hypothetical: when a caller gives up before the planner does, the Dagster job keeps running and its `JOB_STORE` entry stays `PENDING`. #1262 addressed the accumulation (pruning at the existing call site); the abandoned work itself still happens.

## Changing any of these

1. Check this table first, and the comment on the value itself — both the ALB parameter and the QP ceiling name each other.
2. Raising `LIF_QUERY_TIMEOUT_SECONDS` past 150 requires raising `LoadBalancerIdleTimeoutSeconds` with it, or the ALB will cut first and the failure will be misreported as CORS.
3. Remember the code defaults. Several differ from the deployed values, so removing an environment variable is a silent change, not a no-op.
4. Update this doc in the same PR.

## Related

- #1263 — this ladder, recorded
- #1172 / #571 — made the planner ceiling configurable and set the deployed 120
- #1050 — the ALB 504 that surfaces as a CORS error
- #1157 — why the translator client is 45s
- #1262 — `JOB_STORE` entries orphaned when a caller gives up first
- #572 — the measured basis for `LIF_SERVICE_REQUEST_TIMEOUT_SECONDS`
