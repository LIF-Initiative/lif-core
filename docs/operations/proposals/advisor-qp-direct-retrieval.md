# Advisor → Query Planner direct retrieval (ADR-0003 implementation plan)

**Status:** Proposed
**Date:** 2026-07-30
**Author:** bjagg
**Tracking issue:** [#1053](https://github.com/LIF-Initiative/lif-core/issues/1053) (spike)
**Decision of record:** [ADR-0003](../../design/adr/general/0003-advisor-queries-query-planner-directly.md)

> Turn ADR-0003 ("internal programmatic consumers retrieve from the Query Planner directly; GraphQL is an external facade, not an internal waypoint") into a sequenced, t-shirt-sized implementation plan. This is the spike deliverable — the plan and the follow-up issues, **not** the code.

## TL;DR

- **Regime A (in-turn token streaming, seconds)** is already designed in [`advisor-streaming.md`](advisor-streaming.md) (#970) and **needs no data-layer change** — it streams the LLM's tokens, not retrieval progress. Ship it first, independently.
- **Regime B (cross-turn async, minutes)** is what ADR-0003 actually unblocks, and it rests on a capability the Query Planner **does not have yet**: partial results. Today the QP is strictly binary — full `List[LIFRecord]` *or* a bare `PENDING`/`COMPLETED` status with no data.
- The retrieval rewire (semantic-search → QP direct) is a modest, valuable step on its own — it removes the GraphQL hop and is the enabling topology — and can land **before** the partial-result work.
- Recommended order: **Regime-A-first**, then the rewire (contract + auth + shared query construction + semantic-search cutover), then partial results + completion push (the QP net-new work), then Regime B in the Advisor.

## Current state (grounded)

The path today (ADR-0003 §Context, confirmed in code):

```
advisor-api → langchain_agent (ask_agent) → MCP tool (semantic-search)
  → builds a GraphQL query STRING → graphql_client (X-API-Key)
  → graphql-org1 → resolver builds {filter, selected_fields} → POST QP /query (sync)
      → cache / orchestrator
```

Findings that shape the plan (file:line):

1. **`/query_async` already exists** — `bases/lif/query_planner_restapi/core.py:155-175` (returns `202` + `Location: /query/{id}/status` + `Retry-After`, or `200` with records). **But the naming is inverted:** the sync `/query` is commented *"temporary… will be removed soon"* (`core.py:101-104`) and `/query_async` is *"will be changed to /query in the future"* (`core.py:151-154`). The GraphQL resolver currently calls the **sync `/query`** (`components/lif/openapi_to_graphql/type_factory.py:814`), which blocks-and-polls up to a **hardcoded 300s → 408** (`core.py:116-117`; the declared `MAX_QUERY_TIMEOUT_SECONDS = 60` is dead code).
2. **No partial results.** The response is strictly binary: `List[LIFRecord]` or `LIFQueryStatusResponse{query_id, status, error_message?}` where `status` is a free-form `str` (not an enum) only ever `PENDING`/`COMPLETED` (`components/lif/datatypes/core.py:119-131`). There is no fragment-level "here's the cached half, the rest is refreshing" representation anywhere.
3. **Completion is all-or-nothing and poll-based over in-memory state.** The Dagster orchestrator POSTs **every** query-plan part in one shot to `/orchestration/results` (`orchestrators/dagster/lif-orchestrator/src/lif_orchestrator/defs/lif_job.py:247-255`); the QP saves them to cache and flips `job.status PENDING→COMPLETED` atomically (`components/lif/query_planner_service/core.py:243-268`). There is **no push** to a waiting consumer — the sync poller notices the flip in a **module-level in-memory `JOB_STORE` dict** (`query_planner_service/core.py:371`), which also means the callback and the poller must be the **same process** (QP can't scale past one instance today).
4. **The QP is unauthenticated** — no middleware anywhere in `bases/lif/query_planner_restapi/` (contrast `bases/lif/api_graphql/core.py:59` which adds `ApiKeyAuthMiddleware`). It's reachable only on internal CloudMap DNS. The orchestrator even sends a bearer token the QP never validates (`lif_job.py:249-250`).
5. **Query construction is forked.** semantic-search builds a GraphQL **string** (`components/lif/semantic_search_service/core.py:411-422`, via `paths_to_graphql_fields` + `to_graphql_literal`); the GraphQL resolver builds a `{filter, selected_fields}` **`LIFQuery` JSON** (`type_factory.py:807-809`, `selected_fields` derived from the GraphQL AST). There is no shared brick that emits a `LIFQuery` — so pointing semantic-search at the QP naively would create a *second* `LIFQuery`-construction path. `LIFQuery` itself is small: `{filter: LIFQueryFilter, selected_fields: List[str]}` (`datatypes/core.py:99-116`), and `selected_fields` is the QP's projection mechanism (so field-selection parity is achievable).
6. **semantic-search has no QP wiring today** — only `LIF_GRAPHQL_API_URL` (`cloudformation/lif-semantic-search-taskdef-includes.yml:4-6`). The QP *is* already on CloudMap for GraphQL to reach (`http://query-planner-${Org}.lif.${Env}.aws:8002`, `cloudformation/lif-graphql-taskdef-includes.yml:2-4`), so the target URL exists — it just isn't injected into semantic-search.
7. **Advisor is non-streaming, single-worker, with a blocking reframe on the event loop.** `ask_agent` does `await agent.ainvoke(...)` (`components/lif/langchain_agent/core.py:186`); the API returns one `ChatMessage` (`bases/lif/advisor_restapi/core.py:239-283`); **no `astream_events`**. `reframe_query_with_identifiers` is a sync `def` doing a blocking `llm.invoke` (`langchain_agent/core.py:238,248-249`) called without `await`/threadpool from the async `ask_agent` (`core.py:177`), on a **single uvicorn worker** (`projects/lif_advisor_api/Dockerfile2:49`). This is #970 risk #2.

## The two regimes

**Regime A — in-turn streaming (≲ tens of seconds).** Stream the LLM's answer tokens as they generate. This is [`advisor-streaming.md`](advisor-streaming.md) / #970 and is **orthogonal to ADR-0003**: it does not touch retrieval — semantic-search still returns a complete result set within the turn. *Confirmed: Regime A ships with no data-layer change.* Its one shared dependency with ADR-0003 is the reframe concurrency fix (risk #2), which either regime's concurrency needs.

**Regime B — cross-turn async (minutes).** Answer immediately from cached fragments with "still refreshing" markers, then re-engage the conversation when the orchestrator refresh lands. This is the regime ADR-0003 exists to unblock, and it is gated on **partial results + a completion push**, both net-new QP capabilities (findings 2–3).

## Design

### 1. Graduate the QP async contract (findings 1)

Make the async job model the **supported, versioned** interface a direct consumer can depend on:

- Resolve the inverted naming: promote the async handler to the canonical path, keep the sync blocking-poll `/query` as a thin backward-compatible shim (the GraphQL resolver keeps working) with a deprecation note, or fold it into a `wait=true` query param on the async endpoint.
- Replace the free-form `status: str` with an **enum** (`PENDING | PARTIAL | COMPLETED | FAILED`), adding `PARTIAL` for §2.
- Fix the dead `MAX_QUERY_TIMEOUT_SECONDS` / hardcoded-300s inconsistency while here.

### 2. Partial-result / pending-fragment model (the Regime-B keystone; findings 2–3)

Net-new QP capability. The async response should be able to carry **present fragments now + descriptors for fragments still refreshing**:

- Response gains a `PARTIAL` status plus, alongside whatever `LIFRecord` data is already cached, a list of **pending-fragment descriptors**: `{fragment_path, orchestrator_job_ref, status, eta?}` — keyed on the same dotted `selected_fields` paths the QP already resolves (`query_planner_service/core.py:81`).
- The orchestrator today posts **all** parts in one callback (`lif_job.py:242-252`); to expose fragments as they land, either have the orchestrator post **per-part** results, or have the QP track per-part expected-vs-arrived and surface the delta. Per-part completion is the bigger of the two changes and is the true keystone.
- `JOB_STORE` must move off the module-level in-memory dict to a **durable, shared store** (finding 3) — required both for partial state that survives and for the QP to scale past one instance.

### 3. Completion notification / push (finding 3)

Today: poll-over-in-memory. For Regime B a consumer needs to learn a pending fragment landed:

- Extend `/orchestration/results` handling so a completed (or per-part) refresh **propagates outward**, not just flips an in-memory flag.
- Consumer-facing channel — **decision needed** (see Open decisions): poll the status endpoint (simplest, works today's shape), SSE-with-resume, WebSocket, or web-push. Recommendation: **poll for the QP↔semantic-search hop** (internal, simple, no long-lived connection), and make the **user-facing** push a separate Advisor concern (§5).

### 4. Own query construction once (finding 5)

Extract the "semantic filter + ranked field paths → `LIFQuery`" mapping into a **shared brick** that both consumers use:

- semantic-search already computes the two ingredients — a pydantic filter and a set of dotted field paths (`semantic_search_service/core.py:411-422`) — so it can emit a `LIFQuery` **directly**, skipping the GraphQL-string step entirely.
- The GraphQL resolver already builds the same `{filter, selected_fields}` shape (`type_factory.py:807-809`); refactor it to assemble the `LIFQuery` through the shared brick too, so there is exactly one construction path (ADR-0003 cost #1).

### 5. semantic-search rewire + Advisor Regime B (findings 6–7)

- Inject `LIF_QUERY_PLANNER_URL` into semantic-search (the CloudMap target already exists, finding 6); replace the `graphql_client` call with a QP async client built on the shared brick. **Keep GraphQL** wired and demoable as its own independent consumer of the QP (ADR-0003 decision).
- Advisor Regime B: return a provisional answer from `PARTIAL` data with pending markers; maintain a **durable per-conversation job/subscription registry**; decide **proactive re-engage vs. silent refresh** (Open decisions). This depends on the Advisor's in-memory `conversation_states`/`InMemorySaver` (`advisor_restapi/core.py:24`) — cross-turn durability is itself a dependency.

### 6. Auth/trust for direct QP consumption (finding 4)

Direct consumption removes GraphQL's `X-API-Key` gate. Add **inbound auth to the QP** — mirror `ApiKeyAuthMiddleware` (as GraphQL/mdr-api do) or the composite `cognito_auth` brick — and issue an internal QP key that semantic-search holds (exactly as it holds `LIF_GRAPHQL_API_KEY` today). Validate the orchestrator's already-sent bearer token while here.

## Dependencies

- **Reframe concurrency fix** (#970 risk #2) — shared precursor for either regime; likely lands inside #970.
- **Durable `JOB_STORE`** and **QP horizontal-scale** (in-memory state) — precursors for partial results.
- **Advisor cross-turn durability** (in-memory `conversation_states`) — precursor for Regime B re-engagement.

## Follow-up issues (proposed breakdown)

Sequenced; sizes per [`t-shirt-sizing.md`](../t-shirt-sizing.md). Suggested epic: **"ADR-0003: Advisor→QP direct retrieval."**

| # | Work item | Size | Depends on |
|---|-----------|:----:|-----------|
| A | **Reframe concurrency fix** — make `reframe` non-blocking (`run_in_threadpool`/async); note single-worker + in-memory-state scaling limits | S | — (may fold into #970) |
| B | **Graduate the QP async contract** — canonical async path, `status` enum, sync `/query` as deprecated shim, fix the 300s/60s inconsistency | M | — |
| C | **QP inbound auth** — add API-key (or cognito) middleware; issue an internal QP key; validate the orchestrator token | M | — |
| D | **Shared query-construction brick** — extract "filter + selected paths → `LIFQuery`"; refactor GraphQL resolver + semantic-search to both build through it | M | B |
| E | **semantic-search → QP direct** — inject `LIF_QUERY_PLANNER_URL`, replace `graphql_client` with a QP async client via brick D; keep GraphQL demoable | L | B, C, D |
| F | **Durable QP job store** — move `JOB_STORE` off the in-memory dict to a shared store; unblock multi-instance QP | M | B |
| G | **QP partial-result model** — `PARTIAL` status + pending-fragment descriptors; per-part orchestration completion (orchestrator + QP) | XL | B, F |
| H | **QP completion propagation** — outward notification when a pending fragment lands (poll/push per decision) | L | F, G |
| I | **Advisor Regime B** — provisional-from-cache + pending markers, durable per-conversation subscription registry, re-engage decision, user-facing push channel | XL | E, G, H |

Regime A (#970 / `advisor-streaming.md`) is **not** in this list — it ships on its own track; only item A is shared.

## Recommendation: Regime-A-first

1. **Ship Regime A now** (#970) — independent, no data-layer change, immediate UX win. Do item **A** (reframe fix) as part of it.
2. **Land the rewire foundation** (B → C → D → E): the Advisor retrieves from the QP directly, GraphQL becomes a peer consumer. Valuable and shippable **without** partial results (semantic-search just waits on the async job like the sync path does today). This realizes ADR-0003's topology.
3. **Build the QP net-new capability** (F → G → H): durable store, partial results, completion propagation.
4. **Deliver Regime B** (I) on top.

This front-loads the low-risk, high-value work (streaming + the topology change) and defers the heavy, uncertain QP partial-result subsystem until the direction is proven end-to-end. The alternative — combined Regime A+B delivery — couples an immediate UX win to the longest-pole QP work and is not recommended.

## Out of scope

Implementation (this is the plan). GraphQL streaming for GraphQL's own external consumers (ADR-0003 alternative, independent). Multi-instance Advisor scaling beyond the state-durability precursor noted above.

## References

- [ADR-0003](../../design/adr/general/0003-advisor-queries-query-planner-directly.md) · [ADR-0002](../../design/adr/general/0002-lif-control-plane-vs-mdr-host.md)
- [`advisor-streaming.md`](advisor-streaming.md) (Regime A, #970) · streaming issue [#970](https://github.com/LIF-Initiative/lif-core/issues/970)
- Code: `bases/lif/query_planner_restapi/core.py`, `components/lif/query_planner_service/core.py`, `components/lif/datatypes/core.py`, `components/lif/semantic_search_service/core.py`, `components/lif/openapi_to_graphql/type_factory.py`, `components/lif/langchain_agent/core.py`
