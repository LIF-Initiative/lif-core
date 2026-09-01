# Issue #715 Code-Change Plan: Configurable LLM Sampling Params

**Companion to:** `docs/design/components/advisor.md` § "LLM invocation tuning study" (findings F4/F5 → recs R1/R2; F7 → R7)
**Issue:** #715 · **Label:** LIF Advisor API
**Status:** Draft plan · **Decisions locked 2026-08-23:** single shared temperature default 0.1 at both call sites; findings homed in `docs/design/components/advisor.md`; Change Set B gets its own GitHub issue

One-line summary: Hoist ChatOpenAI sampling params into `LIF_ADVISOR_LLM_*` env vars applied at both call sites (defaulting temperature to 0.1 so the query reframer stops running at OpenAI's server default 1.0), wire through all deployment surfaces, plus an optional second change filtering reference-data paths before TOP_K truncation.

---

## Goals

1. All generation-side knobs (`temperature`, `top_p`, `presence_penalty`, `frequency_penalty`) env-configurable for every `ChatOpenAI` instantiation.
2. Eliminate the hidden temp-1.0 reframer (findings F4): both call sites share one configured value.
3. Defaults land on bjagg's recommended correctness-focused profile.

## Non-goals

- Changing retrieval quality mechanisms (embedding text, MDR descriptions → R4 follow-up ticket).
- Switching providers / adding sampling `top_k` (not supported by OpenAI chat API).
- Tuning memory knobs (`LIF_ADVISOR_MESSAGES_TO_KEEP` etc.).

## Change Set A — env-driven sampling params (primary)

### A1. `components/lif/langchain_agent/core.py`

Add module-level reads alongside the existing block (:44–48):

```python
LLM_TEMPERATURE = float(os.environ.get("LIF_ADVISOR_LLM_TEMPERATURE", "0.1"))
LLM_TOP_P = float(os.environ.get("LIF_ADVISOR_LLM_TOP_P", "1.0"))
LLM_PRESENCE_PENALTY = float(os.environ.get("LIF_ADVISOR_LLM_PRESENCE_PENALTY", "0"))
LLM_FREQUENCY_PENALTY = float(os.environ.get("LIF_ADVISOR_LLM_FREQUENCY_PENALTY", "0"))
```

Apply at both sites:

| Site | Line | Today | Becomes |
|---|---|---|---|
| Agent model (`create_agent_with_memory`) | :123 | `temperature=0.0` | `temperature=LLM_TEMPERATURE, top_p=LLM_TOP_P, presence_penalty=..., frequency_penalty=...` |
| Reframer model (`reframe_query_with_identifiers`) | :259 | *(nothing → server default 1.0)* | same four params |

Defaults rationale (revised after live validation, advisor.md Part A): identifier/type/format fidelity was perfect at *every* temperature tested including 1.0, so this change is justified by **consistency/reproducibility**, not correctness safety — lower risk than originally framed. Measured reframer output stability (mean pairwise Jaccard) improves monotonically as temperature drops: 0.750 @ 1.0 → 0.831 @ 0.7 → 0.844 @ 0.3 → 0.888 @ 0.1 → 0.929 @ 0.0. Temp `0.1` sits in bjagg's recommended 0.1–0.3 range, captures most of the stability gain without 0.0's residual nondeterminism (even T=0 showed min pairwise Jaccard 0.814). `top_p=1.0`; penalties `0`. Net effect vs today: agent 0.0→0.1 (behavioral delta minimal), reframer 1.0→0.1 (the fix). Single shared value across both sites by decision — splitting values would need two env pairs for negligible benefit.

Note: keep the existing `# ty: ignore[unknown-argument]` comment style on the ChatOpenAI lines — stubs may flag the new kwargs.

### A2. Deployment wiring (env passthrough only)

| File | Anchor |
|---|---|
| `development/docker-compose.yml` | advisor-api environment block :177–182 |
| `development/advisor-demo-1org/docker-compose.yml` | :128–133 |
| `development/advisor-demo-3orgs/docker-compose.yml` | :249–254 |
| `deployments/advisor-demo-docker/docker-compose.yml` | :421–426 |
| `cloudformation/lif-advisor-api-taskdef-includes.yml` | after `LIF_ADVISOR_LLM_MODEL_NAME` :10 |
| `development/scripts/run_lif_advisor_restapi.sh` | exports :11 |

Pattern: `LIF_ADVISOR_LLM_TEMPERATURE: ${LIF_ADVISOR_LLM_TEMPERATURE:-0.1}` etc., mirroring neighboring entries.

### A3. Tests

- New unit tests in `test/components/lif/langchain_agent/test_core.py` (currently a stub) asserting the env parsing/default fallbacks via `monkeypatch.setenv` — pattern per `test/components/lif/lif_schema_config/test_core.py:67`.
- No live-LLM assertions (offline CI).

### A4. Docs

- Update env-var tables in `docs/design/adr/ai_architecture/0001-ai-architecture-overview.md` (~:320).
- Findings live in `docs/design/components/advisor.md` (already committed on this branch); this PR's doc edits link there and record the chosen defaults.

### Rollout notes

- ECS: new keys must be added to the task-def includes before deploy; values default safely if absent, so image/taskdef ordering is not fragile.
- Compose demos pick up defaults automatically.

## Change Set B — filter reference-data paths before TOP_K truncation (optional, separate PR)

Findings F2: `semantic_search_service/core.py:396` truncates to top_k *before* `filter_paths_for_graphql` (:416) discards non-queryable roots — ~25–30% of slots wasted.

Change: filter paths by `config.reference_data_roots` first, then slice `[:top_k]`.

In `run_semantic_search` (`:366`), `config` is `Optional[LIFSchemaConfig] = None` (`:374`) and
`reference_data_roots` is not bound in that scope, so it needs the same `None` guard
`filter_paths_for_graphql` uses at `:336`:

```python
if config is None:
    config = LIFSchemaConfig()
reference_data_roots = config.reference_data_roots

queryable_idx = [
    int(i)
    for i in np.argsort(-sims)
    if leaves[int(i)].json_path.split(".")[0] not in reference_data_roots
]
idxs = queryable_idx[:top_k]
```

Risk note: the function returns the GraphQL response (`:429`), not `results`, so the effect is **more**
queryable Person paths surviving into `graphql_paths` — a wider requested field list and a larger response
payload, not fewer discarded-path entries. Re-run the spike sweep after landing to re-evaluate whether
k=200 can drop toward 150 (advisor.md rec R3). **Decided: gets its own GitHub issue** — #715 is labeled Advisor API and this lives in semantic_search_service.

## Follow-up candidates — Change Set C sketch (not in this PR)

Maps to advisor.md finding F7 / rec R7: reframing helps vague queries hugely (skills 50→17, relocate 87→43) but regresses strong-signal ones whose raw wording already matches schema language (advising session 1→49). Candidate designs, in rough preference order:

1. **Dual-query fusion** — retrieve with both raw and reframed queries, merge by best gold rank or reciprocal-rank fusion (RRF).
2. **Constrained reframer prompt** — append synonyms without rewording, so a direct match survives alongside expansions.
3. **Conditional expansion** — skip reframing when the query already contains schema vocabulary (needs a cheap detector).

Where it lands is TBD (semantic_search_service vs langchain_agent); file as follow-up issue(s) when Set A/B are in flight.

## Cleanup rider (tiny, same PR as A or B)

- `Organization` is listed as an additional root that no longer exists in the MDR model → startup ERROR log noise. It appears in **two** places and both must change: the dataclass default at `lif_schema_config/core.py:92` and the `from_environment()` fallback string at `:178` (`os.getenv("LIF_GRAPHQL_ROOT_NODES", "Course,Organization,Credential")`). The production path is `from_environment()` — `semantic_search_mcp_server/core.py:35` and `api_graphql/core.py:24` — and `LIF_GRAPHQL_ROOT_NODES` is set in no compose file, script, or CloudFormation template, so editing only `:92` changes nothing deployed and the ERROR noise persists. Either drop it from both, or leave both with a comment pointing at MDR. (Flagged in findings appendix.)

## Verification checklist

1. `uv run pre-commit run --files <changed files>` (ruff, cspell, ty, pytest).
2. `uv run pytest test/components/lif/langchain_agent test/components/lif/lif_schema_config`.
3. Local smoke: `development/scripts/run_lif_advisor_restapi.sh` with `LIF_ADVISOR_LLM_TEMPERATURE=0.3` unset/set; confirm log line shows reframer responses stable across repeats (identifier strings preserved verbatim). Concrete expectation from Part A: at T=0.1 repeat responses are near-identical (mean pairwise Jaccard ≈ 0.89; anything in the 0.85+ band is consistent with the measurement), identifiers and the "I am…" format preserved in 100% of samples.
4. Compose demo (`development/advisor-demo-1org`) boots with no new required vars.

## Open questions — all resolved 2026-08-23

- ~~Final resting place for the findings write-up?~~ → `docs/design/components/advisor.md`.
- ~~Defaults temp `0.1` shared vs split agent/reframer values?~~ → Single shared value, default `0.1`.
- ~~Does Change Set B need its own GH issue given the label mismatch?~~ → Yes, its own issue.

Remaining pre-PR work: implement Change Set A (+ rider), open the Set B issue.
