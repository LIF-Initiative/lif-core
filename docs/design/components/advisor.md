# Advisor API

Advisor API (`bases/lif/advisor_restapi/`): demo-tier FastAPI chat backend that answers natural-language questions about a learner's record via a LangGraph agent whose retrieval runs through the Semantic Search MCP server. Includes the #715 LLM-invocation tuning study (sampling params, TOP_K sweep, live reframer validation).

**Status:** Demo tier per [ADR 0005](../adr/general/0005-product-surfaces-and-component-tiers.md) — the Advisor showcases the product-tier MCP server; it is not deployed to customers on its own.

## Purpose

Give evaluators a credentialed chatbot over an individual learner's LIF record: log in as a demo persona, ask questions ("what are my skills?", "can you summarize my last advising session?"), get grounded answers plus tool-call/token accounting.

## Interfaces

**HTTP** — port 8004 (`projects/lif_advisor_api/Dockerfile2`). JSON/JWT session auth issued by this service via the shared `auth` brick (`components/lif/auth`) against `demo_personas`; no external IdP in the demo path.

| Method | Path | Purpose |
|---|---|---|
| POST | `/login`, `/refresh-token`, `/logout` | Session lifecycle |
| GET | `/me`, `/initial-message` | User details; greeting |
| POST | `/start-conversation`, `/continue-conversation` | Chat turns |

**Outbound:** OpenAI chat models (`langchain-openai`) and the Semantic Search MCP server (`langchain-mcp-adapters`) for schema-leaf retrieval — see [`semantic-search.md`](semantic-search.md). Retrieval topology decisions (Query Planner direct) are [ADR 0003](../adr/general/0003-advisor-queries-query-planner-directly.md); the full component/env map is [ADR 0001](../adr/ai_architecture/0001-ai-architecture-overview.md).

## Internal structure

- `bases/lif/advisor_restapi/core.py` — FastAPI app, session/user helpers, per-user conversation registry.
- `components/lif/langchain_agent/core.py` — `LIFAIAgent`: builds MCP toolset + one LangGraph react agent per task type (`LIF_ADVISOR_AGENT_TASKS`) sharing an `InMemorySaver`; each turn **reframes** the user query (identifier-preserving rewrite) before invoking the agent. Memory summarization knobs `LIF_ADVISOR_MESSAGES_TO_KEEP` / `_TRIMMED_MESSAGES_SIZE` / `_MAX_CONVERSATION_SIZE` / `_MAX_SUMMARY_SIZE` (`core.py:44-48`).
- Two `ChatOpenAI` call sites: agent model (`core.py:123`, `temperature=0.0`) and reframer model (`core.py:259`, temperature unset → OpenAI server default 1.0). See tuning study below.
- Single uvicorn worker; the reframe is a synchronous blocking call on the event loop — tracked with streaming work in [`advisor-streaming.md`](../../operations/proposals/advisor-streaming.md) (#970).

---

## LLM invocation tuning study (issue #715 spike, 2026-08-21)

Empirical review of every LLM/retrieval knob in the Advisor path: offline TOP_K sweep over a replicated production pipeline, then live gpt-4.1-mini validation of sampling params (125-call temperature sweep + end-to-end reframer retrieval test). Raw scripts and result JSONs are archived in `.claude/plans/artifacts/` (gitignored working space).

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

### Recommendations

1. **R1 (high)** — Env-configurable generation params (`LIF_ADVISOR_LLM_TEMPERATURE`, `_TOP_P`, `_PRESENCE_PENALTY`, `_FREQUENCY_PENALTY`) applied at **both** ChatOpenAI sites; default temperature `0.1`. Justification is consistency/reproducibility across the two call sites (variance 0.750→0.888), not identifier safety. Plan: `.claude/plans/issue-715-code-changes.md`.
2. **R2 (high)** — Filter non-queryable reference-data paths **before** top_k truncation (or raise effective k). Needs its own issue — lives in `semantic_search_service`, #715 is labeled Advisor API.
3. **R3 (medium)** — Keep `SEMANTIC_SEARCH__TOP_K=200` short-term; re-run the sweep after R2 lands, consider 150.
4. **R4 (medium)** — Follow-up ticket: embed `json_path + description` instead of description-only; separately push MDR owners to enrich boilerplate leaf descriptions (`Relocation.*`, `RemoteWork.*`, `Proficiency.*`). Addresses F3, the actual ceiling.
5. **R5 (low)** — Re-derive defaults as the schema grows (the "137 attributes" assumption in old notes is stale: 186 Person / 247 total today).
6. **R6 (low)** — Record chosen values in the AI architecture ADR ([ADR 0001](../adr/ai_architecture/0001-ai-architecture-overview.md)), which predates these findings.
7. **R7 (medium)** — Follow-up ticket: tame reframing's regression tail (F7) — dual-query fusion (search raw + reframed, merge by best rank or reciprocal-rank fusion), or a constrained reframer prompt that appends synonyms without rewording; test skipping expansion when the query already contains schema vocabulary.

## Operational notes

- Demos: `development/advisor-demo-{1org,3orgs}/docker-compose.yml`, `deployments/advisor-demo-docker/docker-compose.yml`; dev stack `development/docker-compose.yml`.
- The synthetic monitor (`.github/workflows/synthetic-e2e.yml`) exercises advisor→retrieval every 2h against demo and has caught real outages — treat it as the regression guard for anything touching this path.
- Experiment artifacts (sweep scripts + raw JSON results) live in gitignored `.claude/plans/artifacts/`; copy them into a permanent location before deleting that directory.
