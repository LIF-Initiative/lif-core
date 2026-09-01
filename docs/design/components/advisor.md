# Advisor API

Version 1.0.0

**Table of Contents**

[Overview](#overview)

[Motivation](#motivation)

[Design Proposal](#design-proposal)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Key Concept](#key-concept)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Interaction with Other LIF Components](#interaction-with-other-lif-components)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Design Assumptions](#design-assumptions)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Design Requirements](#design-requirements)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Performance](#performance)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Concurrency](#concurrency)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[High Availability](#high-availability)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[High Level Design](#high-level-design)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Interface](#interface)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Workflow Model](#workflow-model)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Configuration](#configuration)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Dependencies](#dependencies)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Exceptions and Errors](#exceptions-and-errors)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Authentication and Session Exceptions](#authentication-and-session-exceptions)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Conversation Exceptions](#conversation-exceptions)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Agent Exceptions](#agent-exceptions)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Example Usage](#example-usage)

[LLM Invocation Tuning Study](#llm-invocation-tuning-study-issue-715-spike-2026-08-21)

[Operational Notes](#operational-notes)

[Possible Future Roadmap Items](#possible-future-roadmap-items)

# Overview

The **Advisor API** (`bases/lif/advisor_restapi/`) is a demo-tier FastAPI chat backend that answers natural-language questions about a learner's record via a LangGraph agent whose retrieval runs through the Semantic Search MCP server. It includes the #715 LLM-invocation tuning study (sampling params, TOP_K sweep, live reframer validation).

**Status:** Demo tier per [ADR 0005](../adr/general/0005-product-surfaces-and-component-tiers.md) — the Advisor showcases the product-tier MCP server; it is not deployed to customers on its own.

**Purpose:** Give evaluators a credentialed chatbot over an individual learner's LIF record: log in as a demo persona, ask questions ("what are my skills?", "can you summarize my last advising session?"), get grounded answers plus tool-call/token accounting.

# Motivation

A learner's record is large, deeply nested, and expressed in schema vocabulary that a human evaluator does not know. Asking a question about it ("am I willing to relocate for a job?") requires more than the query planner can store in a single request — the answer lives across schema leaves (`PositionPreferences.Relocation.*`, `RemoteWork`, `Proficiency`) whose names rarely match natural language. The Advisor exists to give evaluators a credentialed conversational surface over the record: it rewrites ("reframes") each question into an identifier-preserving query, retrieves the relevant schema leaves through the Semantic Search MCP server, and grounds a chat-model answer in that retrieved context with token/cost accounting. Without this component, evaluators would have to hand-build parallel queries against the raw MDR model to reach the same facts.

# Design Proposal

## Key Concept

### LIFAIAgent

`LIFAIAgent` (`components/lif/langchain_agent/core.py`) builds an MCP toolset plus one LangGraph react agent per task type (`LIF_ADVISOR_AGENT_TASKS`), all sharing an `InMemorySaver` so a conversation's history is preserved across turns within the process lifetime.

### Query reframer

Before each agent invocation, the user's raw query is **reframed** — rewritten in an identifier-preserving way (synonym expansion toward schema language while keeping the Person/entity identifiers verbatim). The reframe step is what lets vague wording ("what are my skills?") reach schema leaves that never mention that phrasing.

### Retrieval

Retrieval runs through the Semantic Search MCP server for schema-leaf retrieval — see [`semantic-search.md`](semantic-search.md). The retrieval topology (Query Planner direct) is decided in [ADR 0003](../adr/general/0003-advisor-queries-query-planner-directly.md); the full component/env map is [ADR 0001](../adr/ai_architecture/0001-ai-architecture-overview.md).

## Interaction with Other LIF Components

- **`auth` brick** (`components/lif/auth`) — session JWTs are issued by this service against `demo_personas`; no external IdP on the demo path.
- **Semantic Search MCP server** (`langchain-mcp-adapters`) — schema-leaf retrieval for grounding.
- **OpenAI chat models** (`langchain-openai`) — the agent model and the reframer model (see [LLM Invocation Tuning Study](#llm-invocation-tuning-study-issue-715-spike-2026-08-21)).
- **Query Planner** — the retrieval endpoint the Semantic Search service targets (ADR 0003).

## Design Assumptions

1. The component is demo tier per [ADR 0005](../adr/general/0005-product-surfaces-and-component-tiers.md) and showcases the product-tier MCP server rather than being a customer-deployed surface.
2. No external IdP is present on the demo path; the service issues its own JWTs against `demo_personas`.
3. The component is stateless across restarts — sessions live in an in-memory, per-user conversation registry on a single uvicorn worker.
4. The only outbound dependencies are OpenAI chat models and the Semantic Search MCP server (which retrieves from the Query Planner directly).
5. The schema leaves carry enough description text to ground retrieval; the study shows description quality — not TOP_K — is the binding constraint (finding F3).
6. The reframer must preserve identifiers verbatim; live validation shows this holds at every sampled temperature (study Part A).

## Design Requirements

### Performance

(Investigation in progress — see [LLM Invocation Tuning Study](#llm-invocation-tuning-study-issue-715-spike-2026-08-21).) The reframe is a synchronous blocking call on the event loop of a single uvicorn worker, and tool responses saturate ~2k tokens/query for k≥50. Streaming the responses is tracked in [`advisor-streaming.md`](../../operations/proposals/advisor-streaming.md) (#970).

### Concurrency

The component should serve concurrent conversations from its single uvicorn worker. Per-user conversation state is kept in process via the `InMemorySaver` and the conversation registry; the blocking reframe call constrains throughput until the streaming work (above) lands.

### High Availability

The demo-tier component should be continuously available for evaluation. The synthetic monitor (`.github/workflows/synthetic-e2e.yml`) exercises the advisor→retrieval path every 2h against demo and has caught real outages — treat it as the regression guard for anything touching this path.

## High Level Design

The service follows today's no-server-side-streaming, request/response design: each chat turn reframes the query, invokes the per-task LangGraph react agent with the conversation's shared memory, and returns a single grounded `ChatMessage` with token/cost accounting. A streaming redesign is proposed in [`advisor-streaming.md`](../../operations/proposals/advisor-streaming.md) (#970).

### Interface

**HTTP** — port 8004 (`projects/lif_advisor_api/Dockerfile2`). JSON/JWT session auth issued by this service via the shared `auth` brick against `demo_personas`; no external IdP in the demo path.

| Method | Path | Purpose |
|---|---|---|
| POST | `/login` | Session login (`username`, `password`) → access + refresh tokens |
| POST | `/refresh-token` | Rotate an access token from a refresh token |
| POST | `/logout` | Session logout |
| GET | `/me` | Current user details |
| GET | `/initial-message` | Greeting message |
| POST | `/start-conversation` | Begin a conversation; returns the greeting `ChatMessage` |
| POST | `/continue-conversation` | Send a question (`message`); returns a grounded `ChatMessage` |
| GET | `/health` | Health check |

**Outbound:** OpenAI chat models (`langchain-openai`) and the Semantic Search MCP server (`langchain-mcp-adapters`) for schema-leaf retrieval — see [`semantic-search.md`](semantic-search.md). Retrieval topology decisions (Query Planner direct) are [ADR 0003](../adr/general/0003-advisor-queries-query-planner-directly.md); the full component/env map is [ADR 0001](../adr/ai_architecture/0001-ai-architecture-overview.md).

**Internal structure:**

- `bases/lif/advisor_restapi/core.py` — FastAPI app, session/user helpers, per-user conversation registry.
- `components/lif/langchain_agent/core.py` — `LIFAIAgent`: builds MCP toolset + one LangGraph react agent per task type (`LIF_ADVISOR_AGENT_TASKS`) sharing an `InMemorySaver`; each turn **reframes** the user query (identifier-preserving rewrite) before invoking the agent. Memory summarization knobs `LIF_ADVISOR_MESSAGES_TO_KEEP` / `_TRIMMED_MESSAGES_SIZE` / `_MAX_CONVERSATION_SIZE` / `_MAX_SUMMARY_SIZE` (`core.py:45-48`).
- Two `ChatOpenAI` call sites: agent model (`core.py:123`, `temperature=0.0`) and reframer model (`core.py:259`, temperature unset → OpenAI server default 1.0). See tuning study below.
- Single uvicorn worker; the reframe is a synchronous blocking call on the event loop — tracked with streaming work in [`advisor-streaming.md`](../../operations/proposals/advisor-streaming.md) (#970).

## Workflow Model

1. **Authenticate** — the evaluator logs in as a demo persona (`POST /login`), receiving a JWT session from the shared `auth` brick.
2. **Greet** — `GET /me` returns user details; `GET /initial-message` or `POST /start-conversation` returns the greeting `ChatMessage`.
3. **Turn** — the evaluator sends a question (`POST /continue-conversation`).
4. **Reframe** — the raw query is rewritten by the reframer model, preserving identifiers, to expand natural-language phrasing toward schema vocabulary.
5. **Invoke agent** — the per-task LangGraph react agent runs with the conversation's shared `InMemorySaver` memory; memory summarization trims older turns per the `LIF_ADVISOR_*` knobs.
6. **Retrieve** — the agent's toolset calls the Semantic Search MCP server for schema-leaf retrieval (Query Planner direct, ADR 0003).
7. **Answer** — the agent model grounds its answer in the retrieved leaves and returns a `ChatMessage` (`content`, `tokens`, `cost`).

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `LIF_ADVISOR_AGENT_TASKS` | — (required) | Agent task types; `ValueError` if unset |
| `LIF_ADVISOR_LLM_MODEL_NAME` | — | Chat model name for both `ChatOpenAI` sites |
| `LIF_ADVISOR_MESSAGES_TO_KEEP` | `4` | Turns kept before summarization |
| `LIF_ADVISOR_TRIMMED_MESSAGES_SIZE` | `384` | Trimmed message window |
| `LIF_ADVISOR_MAX_CONVERSATION_SIZE` | `2048` | Conversation size cap (Python fallback is `384`) |
| `LIF_ADVISOR_MAX_SUMMARY_SIZE` | `1024` | Summarized-reminder size cap (Python fallback is `128`) |
| `SEMANTIC_SEARCH__TOP_K` | `200` | Retrieval result count (schema leaves) |
| `SEMANTIC_SEARCH__MODEL_NAME` | `all-MiniLM-L6-v2` | Embedding model for retrieval |

The `Default` column is the **deployed** value. `MESSAGES_TO_KEEP` and `TRIMMED_MESSAGES_SIZE` match the Python fallbacks in `langchain_agent/core.py:45-48`, but the two size caps do not: every deployment surface overrides them to `2048`/`1024` — `development/docker-compose.yml:181-182`, `development/advisor-demo-1org/docker-compose.yml:132-133`, `development/advisor-demo-3orgs/docker-compose.yml:253-254`, `deployments/advisor-demo-docker/docker-compose.yml:425-426`, `cloudformation/lif-advisor-api-taskdef-includes.yml:17,19`, and `development/scripts/run_lif_advisor_restapi.sh:14-15`. No running advisor has used the `384`/`128` fallbacks.

Generation-side sampling knobs (`temperature`, `top_p`, `presence_penalty`, `frequency_penalty`) are not configurable today — the agent is hardcoded to `0.0` and the reframer runs at the OpenAI server default `1.0`. Making them env-configurable at both call sites (default `temperature=0.1`) is recommendation **R1** — see [Possible Future Roadmap Items](#possible-future-roadmap-items).

## Dependencies

- `langchain-openai` (~0.3 verified) — the two `ChatOpenAI` call sites.
- `langchain-mcp-adapters` — MCP toolset for Semantic Search.
- Semantic Search MCP server + Query Planner (ADR 0003 topology) — retrieval.
- `auth` brick (`components/lif/auth`) — `demo_personas` session JWTs.
- OpenAI API (external) — chat model inference.
- Configuration/architecture context: [ADR 0001](../adr/ai_architecture/0001-ai-architecture-overview.md), [ADR 0003](../adr/general/0003-advisor-queries-query-planner-directly.md), [ADR 0005](../adr/general/0005-product-surfaces-and-component-tiers.md).

## Exceptions and Errors

### Authentication and Session Exceptions

Session lifecycle failures raise HTTP 400/401/404 (`bases/lif/advisor_restapi/core.py`):

- **401** — invalid credentials (login); invalid/revoked/expired refresh tokens.
- **404** — user not found.

### Conversation Exceptions

Chat failures raise HTTP 400:

- **400** — conversation not initialized (`start-conversation` required first).
- **400** — conversation not started.

### Agent Exceptions

Agent construction/use failures (`components/lif/langchain_agent/core.py`):

- **`ValueError`** — `LIF_ADVISOR_AGENT_TASKS` not set at setup.
- **`RuntimeError`** — agent invoked before `setup()`.

## Example Usage

```
curl -X POST localhost:8004/login \
  -H 'Content-Type: application/json' \
  -d '{"username": "person1", "password": "..."}'
# → { "success": true, "user": {...}, "access_token": "...", "refresh_token": "..." }

curl -X POST localhost:8004/start-conversation \
  -H "Authorization: Bearer $ACCESS_TOKEN"
# → ChatMessage greeting: { "content": "...", "tokens": N, "cost": 0.0 }

curl -X POST localhost:8004/continue-conversation \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message": "What are my skills?"}'
# → grounded ChatMessage: { "content": "...", "tokens": N, "cost": 0.xx }
```

# LLM Invocation Tuning Study (issue #715 spike, 2026-08-21)

Empirical review of every LLM/retrieval knob in the Advisor path: offline TOP_K sweep over a replicated production pipeline, then live gpt-4.1-mini validation of sampling params (125-call temperature sweep + end-to-end reframer retrieval test). **The figures below are a one-shot measurement and are not reproducible from this repository.** The sweep scripts and raw result JSONs were written to a local, gitignored working directory (`.claude/plans/artifacts/`) that was not preserved, so nothing in source control regenerates them. Treat every number here as a point-in-time observation of the 2026-08-21 schema and model, not as a regression baseline; re-measuring means rebuilding the harness.

Context: [bjagg's issue comment](https://github.com/LIF-Initiative/lif-core/issues/715) suggested `temperature 0.1–0.3 · top_p 1.0 · top_k 150–250 · penalties 0` — "focus on correctness, not creativity." Note his `top_k` means retrieval result count here (`SEMANTIC_SEARCH__TOP_K`); OpenAI's chat API has no sampling `top_k`.

### Inventory of invocation surfaces (pre-change)

| Knob | Where set | Value | Configurable? |
|---|---|---|---|
| Retrieval `TOP_K` | `components/lif/lif_schema_config/core.py:111,184` | `200` | Yes — `SEMANTIC_SEARCH__TOP_K` |
| Embedding model | same, :110 | `all-MiniLM-L6-v2` | Yes — `SEMANTIC_SEARCH__MODEL_NAME` |
| Agent temperature | `components/lif/langchain_agent/core.py:123` | `0.0` hardcoded | No |
| Reframer temperature | same, :259 | unset → server default **1.0** | No |
| `top_p`, presence/frequency penalty | nowhere | server defaults (1.0 / 0 / 0) | No |
| Memory sizes | `langchain_agent/core.py:45-48` | 4/384/384/128 | Yes — `LIF_ADVISOR_*` |

Verified against langchain-openai ~0.3: `ChatOpenAI(temperature=None)` omits the param, so the reframer genuinely ran at 1.0, hotter than the commonly assumed 0.7.

### Retrieval baseline (offline sweep)

Replicated pipeline: MDR OpenAPI → schema leaves for configured roots → `leaf.description` embeddings (`all-MiniLM-L6-v2`) → cosine ranking; 15 realistic advisor queries, 53-leaf gold set. Index today: Person 186 leaves + Course 14 + Credential 47 = **247** (configured `Organization` root doesn't exist in the MDR model — startup ERROR noise).

Recall@k: k=10 → 34%, 50 → 45%, 100 → 62%, 150 → 81%, 186 → 91%, 200 → 92.5%.

- The original bump 10→200 was correct (two-thirds of relevant fields missed at k=10) but k≥150 ≈ return-everything: 200/247 = 81% of the index per query.
- **~25–30% of top-k slots are wasted**: truncation to top_k happens *before* `filter_paths_for_graphql` discards non-queryable reference-data roots (`semantic_search_service/core.py:396` slices before filtering at :416).
- Tool responses saturate ~2k tokens/query for k≥50 (whole populated record regardless of question).
- **The binding constraint is description quality, not TOP_K**: rank 1–10 gold leaves have 0% generic-boilerplate descriptions; rank 151+ golds are 90% boilerplate (`informationSource*`, "primary key identifier"). E.g., `PositionPreferences.Relocation.*` never mentions relocation in its descriptions, so "am I willing to relocate?" ranks its gold leaf #87 with negative similarity. Embedding richer text (json_path + description) or enriching MDR descriptions is higher-leverage than any further k tuning.

### Generation side (live validation, gpt-4.1-mini)

**Part A — reframer fidelity × temperature** (exact production prompt; 5 queries × 5 repeats × 5 temperatures):

| temp | identifier preserved | format ("I am…") | mean pairwise Jaccard (stability) |
|---|---|---|---|
| 1.0 | 100% | 100% | 0.750 |
| 0.7 | 100% | 100% | 0.831 |
| 0.3 | 100% | 100% | 0.844 |
| 0.1 | 100% | 100% | 0.888 |
| 0.0 | 100% | 100% | 0.929 |

Fidelity was perfect at **every** temperature including 1.0 — the feared dropped/altered identifiers did not materialize (n=25/temp). Even T=0 isn't fully deterministic (min observed pairwise Jaccard 0.814). The case for low temperature is therefore **output stability → consistent downstream retrieval**, not correctness safety.

**Part B — end-to-end retrieval effect of real LLM reframing** (best gold rank; raw → reframed@1.0 → reframed@0.1):

| Query | raw | @1.0 | @0.1 |
|---|---|---|---|
| What are my skills? | 50 | 17 | 17 |
| What courses have I taken? | 3 | 2 | 2 |
| I need to update my email address. | 1 | 1 | 2 |
| Am I willing to relocate for a job? | 87 | 43 | 43 |
| Can you summarize my last advising session? | 1 | 8 | 49 |

Synonym expansion is strongly **query-dependent**: big wins where raw wording misses schema language (skills −33 ranks, relocate −44), but regressions when the raw query already matches schema vocabulary perfectly (advising session 1→49 at T=0.1 — injected identifiers/synonyms dilute a direct match). Reframer variance directly becomes retrieval variance: temperature choice flipped the borderline advising query (rank 8 vs 49). This reverses an earlier offline impression that manual synonym expansion slightly hurt (50→54); real LLM expansion helps weak-signal queries substantially.

### Findings

- **F1** — TOP_K 10→200 was right but is now blunt: k≥150 returns ~everything; marginal recall past ~150 is boilerplate-driven.
- **F2** — Truncation happens before reference-data filtering; ~25–30% of slots discarded post-hoc.
- **F3** — Description quality is the retrieval ceiling, not TOP_K.
- **F4** — Reframer ran at server-default temperature 1.0 while agent ran 0.0 — inconsistent. Live data shows this was never a correctness risk (fidelity held at 1.0); it is a **reproducibility/stability** concern (Jaccard 0.750 at 1.0 vs 0.888 at 0.1).
- **F5** — No generation-side knob (temp/top_p/penalties) is configurable; hardcode-or-default.
- **F6** — Tool responses saturate ~2k tokens/query for k≥50; k=200 buys field-list breadth, not data coverage.
- **F7** — Reframing has a query-dependent effect: large gains on vague queries, real regressions when the raw query already uses schema language.
- **F8** — Even temperature 0 does not make the reframer deterministic (observed min pairwise Jaccard 0.814).

# Operational Notes

- Demos: `development/advisor-demo-{1org,3orgs}/docker-compose.yml`, `deployments/advisor-demo-docker/docker-compose.yml`; dev stack `development/docker-compose.yml`.
- **Experiment artifacts were not preserved.** The sweep scripts and raw JSON results lived in a local, gitignored `.claude/plans/artifacts/` directory that no longer exists, so the study above cannot be re-run from this repo. Any re-measurement (for example the post-R2 TOP_K sweep called for by R3) starts from a rebuilt harness — commit that harness under `test/` so the next round is reproducible.

# Possible Future Roadmap Items

Mapped from the study findings to concrete work; where the change is scoped, the owning issue/plan is linked. The supporting figures are a one-shot measurement (see above), so any recommendation whose threshold depends on them — R1's default temperature, R3's `TOP_K` value — should be re-measured against a committed harness before it is treated as settled.

1. **R1 (high, finding F4/F5)** — Env-configurable generation params (`LIF_ADVISOR_LLM_TEMPERATURE`, `_TOP_P`, `_PRESENCE_PENALTY`, `_FREQUENCY_PENALTY`) applied at **both** ChatOpenAI sites; default temperature `0.1`. Justification is consistency/reproducibility across the two call sites (variance 0.750→0.888), not identifier safety. Plan: `.claude/plans/issue-715-code-changes.md`.
2. **R2 (high, finding F2)** — Filter non-queryable reference-data paths **before** top_k truncation (or raise effective k). Needs its own issue — lives in `semantic_search_service`, #715 is labeled Advisor API.
3. **R3 (medium, finding F1)** — Keep `SEMANTIC_SEARCH__TOP_K=200` short-term; re-run the sweep after R2 lands, consider 150.
4. **R4 (medium, finding F3)** — Follow-up ticket: embed `json_path + description` instead of description-only; separately push MDR owners to enrich boilerplate leaf descriptions (`Relocation.*`, `RemoteWork.*`, `Proficiency.*`). Addresses F3, the actual ceiling.
5. **R5 (low)** — Re-derive defaults as the schema grows (the "137 attributes" assumption in old notes is stale: 186 Person / 247 total today).
6. **R6 (low)** — Record chosen values in the AI architecture ADR ([ADR 0001](../adr/ai_architecture/0001-ai-architecture-overview.md)), which predates these findings.
7. **R7 (medium, finding F7)** — Follow-up ticket: tame reframing's regression tail — dual-query fusion (search raw + reframed, merge by best rank or reciprocal-rank fusion), or a constrained reframer prompt that appends synonyms without rewording; test skipping expansion when the query already contains schema vocabulary.