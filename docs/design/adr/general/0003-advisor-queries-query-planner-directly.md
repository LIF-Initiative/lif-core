# ADR 0003: Advisor/MCP retrieval talks to the Query Planner directly; GraphQL is an external query facade, not an internal waypoint

Date: 2026-07-16

## Status

Proposed

## Context

The Advisor's retrieval path today is:

```
advisor-api → langchain_agent → MCP tool (semantic-search)
  → builds a GraphQL query string, calls graphql_client
  → graphql-org1 (GraphQL API)
      → resolver POSTs a LIFQuery to the Query Planner  (openapi_to_graphql/type_factory.py → QP /query)
          → cache / orchestrator
```

So GraphQL sits **in the middle** of every Advisor retrieval. This was convenient (the `graphql_client` brick was the ready-made way in) and demonstrates the GraphQL component working, but on reflection GraphQL and the Query Planner are not a pipeline — they are a **facade and an engine**:

- **GraphQL (`api_graphql`)** is an MDR-schema-generated, typed, self-describing, *ad-hoc* query surface. Its resolvers do nothing but shape a `LIFQuery`, `POST` it to the Query Planner, and shape the response. It is transactional by design.
- **Query Planner (`query_planner_restapi`)** is the actual retrieval engine — routing, cache, orchestration — and it already exposes an asynchronous job model (`/query_async` → `202` + status `Location`, `/query/{id}/status`, and an orchestrator completion callback `/orchestration/results`).

Two forces expose the mismatch of putting GraphQL in the Advisor's hot path:

1. **Consumer/contract mismatch.** GraphQL is the right contract for *external, exploratory, third-party* consumers who want to ask for arbitrary shapes. The Advisor is an *internal, programmatic, latency- and streaming-sensitive* consumer with fixed access patterns; it wants LIF records with progress/partial semantics. Routing it through a flexible ad-hoc query language is using the wrong tool for a fixed internal call.
2. **Variable latency + partial data.** LIF retrieval ranges from milliseconds (cache hit) to minutes (a partial hit that kicks off an orchestrator refresh). GraphQL's transactional response cannot express "here is the cached half now; the rest is refreshing and will arrive in ~2 minutes." The Query Planner's async job model can. (Today the QP is still binary — full results *or* `PENDING` with no data, and the sync `/query` blocks-and-polls up to 300s → 408 — so partial results are themselves a QP capability yet to be built; see [#970](https://github.com/LIF-Initiative/lif-core/issues/970) and the streaming design discussion.)

LIF's design goal is independent, composable microservices (see [ADR 0002](0002-lif-control-plane-vs-mdr-host.md)). Forcing every internal consumer through GraphQL makes GraphQL a chokepoint rather than one component among peers.

## Decision

**Internal programmatic consumers retrieve LIF data from the Query Planner directly; GraphQL remains an external query facade and a peer consumer of the same Query Planner, not a mandatory internal waypoint.**

Concretely:

- The Advisor's retrieval (via the **semantic-search MCP server**, which is both the current GraphQL client *and* the place the query is constructed) targets the **Query Planner's async `LIFQuery` interface** (`/query_async` + status/callback) instead of GraphQL.
- **GraphQL is retained** as the typed, self-describing query surface for external/ad-hoc consumers, and is exercised/demonstrated as its own consumer of the Query Planner — decoupled from the Advisor.
- This is the enabling topology for the Advisor's progress/partial/streaming work: partial results + pending-fragment markers + completion push flow naturally from the QP's async model, because GraphQL's transactional limitation is no longer in the path.

## Alternatives

- **Keep GraphQL in the Advisor path and add GraphQL streaming** (`@defer`/`@stream` incremental delivery, or subscriptions). Rejected as the primary path: `@defer`/`@stream` defer fields within a single response lifecycle (seconds), not minutes-later orchestrator refreshes; subscriptions are a separate long-lived channel that would still front the same QP async model — extra machinery to preserve a hop the Advisor does not need. GraphQL streaming remains worthwhile *for GraphQL's own external consumers*, independent of this decision.
- **Drop GraphQL entirely, make the QP the only query interface.** Rejected: GraphQL is a legitimate, valuable *product* surface for external integrators (typed, flexible, self-documenting). This ADR narrows GraphQL's role, it does not remove it.
- **Status quo (MCP → GraphQL → QP).** Rejected: it couples the Advisor to a transactional contract that cannot express partial/streaming, adds a hop and a query-string round-trip, and makes GraphQL a mandatory internal chokepoint.

## Consequences

Positive:

- Unblocks partial-result and progress/streaming UX for the Advisor (the "Regime B" async-retrieval work) without fighting GraphQL's transactional model.
- More faithful to LIF's microservice-independence goal: the Query Planner becomes a first-class, directly-consumable service; GraphQL becomes one consumer among several.
- Removes a network hop and a query-string build/parse round-trip from the Advisor's hot path.

Costs / things that must be owned so this does not become debt:

1. **Query construction must be owned once.** The "semantic filter → query" logic currently lives as GraphQL-string templating inside semantic-search. Moving to QP `LIFQuery` objects risks *two* divergent query-construction paths (GraphQL's and the Advisor's). Keep it in a shared brick or push it into the QP request model — do not fork it.
2. **The QP async contract must graduate from "temporary."** `/query` is commented as temporary and `/query_async` as the future; a direct Advisor dependency makes the async `LIFQuery` interface a supported, versioned contract (a good forcing function).
3. **The QP needs a first-class auth/trust story** for direct consumption. Today it is internal and reached via GraphQL (which holds the API key).
4. **Field selection / response shaping parity.** GraphQL gives semantic-search field selection today; the QP `LIFQuery`/`LIFRecord` contract must express desired fields or the Advisor over-fetches. MDR remains the schema source of truth on the QP side regardless.
5. **Partial results are a new QP capability.** Returning cached fragments now + pending-fragment descriptors + an outward completion notification is net-new work on the QP; this ADR sets the direction, not the implementation.

## References

- [#970 — Advisor end-to-end streaming](https://github.com/LIF-Initiative/lif-core/issues/970) and the streaming/progress design discussion (Regime A in-turn streaming vs Regime B cross-turn async).
- [ADR 0002 — LIF control plane vs MDR host](0002-lif-control-plane-vs-mdr-host.md) (component-independence framing).
- Code paths: `bases/lif/semantic_search_mcp_server/core.py`, `components/lif/semantic_search_service/core.py` (GraphQL client), `components/lif/openapi_to_graphql/type_factory.py` (GraphQL resolver → QP), `bases/lif/query_planner_restapi/core.py` (`/query`, `/query_async`, `/query/{id}/status`, `/orchestration/results`).
