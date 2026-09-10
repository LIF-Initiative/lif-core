# Configurable LLM sampling params for the Advisor (#715 implementation plan)

**Status:** Proposed
**Date:** 2026-09-09
**Author:** dereck-symmetry
**Tracking issue:** [#715](https://github.com/LIF-Initiative/lif-core/issues/715) (spike)
**Companion to:** [`advisor-api.md`](../../design/components/advisor-api.md) § "LLM invocation tuning study" (findings F4/F5 → rec R1; F2 → rec R2; F7 → rec R7)

> Turn the #715 tuning study into a sequenced change plan. **Reopened 2026-09-01 (review of #1173):** the temperature *default* is no longer locked — see Open questions. What remains settled: a single shared value across both call sites (not split); findings homed in [`advisor-api.md`](../../design/components/advisor-api.md); Change Set B gets its own GitHub issue.

One-line summary: Hoist ChatOpenAI sampling params into `LIF_ADVISOR_LLM_*` env vars applied at both call sites (so the query reframer stops running at OpenAI's server default 1.0; the default value itself is an open question — `0.1` below is a placeholder), wire through all deployment surfaces, plus an optional second change filtering reference-data paths before TOP_K truncation.

---

## Goals

1. All generation-side knobs (`temperature`, `top_p`, `presence_penalty`, `frequency_penalty`) env-configurable for every `ChatOpenAI` instantiation.
2. Eliminate the hidden temp-1.0 reframer (findings F4): both call sites share one configured value.
3. Both sites carry the *same* explicit values. The temperature **value itself is not chosen by this plan** — see Open questions.

## Non-goals

- Changing retrieval quality mechanisms (embedding text, MDR descriptions → R4 follow-up ticket).
- Switching providers / adding sampling `top_k` (not supported by OpenAI chat API).
- Tuning memory knobs (`LIF_ADVISOR_MESSAGES_TO_KEEP` etc.).

## Change Set A — env-driven sampling params (primary)

### A1. `components/lif/langchain_agent/core.py`

Read the knobs **at call time**, not at import. The neighboring block at `:44–48` is module-level, but that shape is untestable here: `monkeypatch.setenv` cannot change a constant already evaluated at import, and `importlib.reload` is ruled out by `CLAUDE.md` → Testing ("avoid `importlib.reload()` in tests — it breaks `isinstance()`/`pytest.raises()` matching"). A helper keeps the reads testable and matches the direction #1191 moved config in:

```python
# PLACEHOLDER — the temperature default is not chosen; see Open questions.
_LLM_TEMPERATURE_DEFAULT = "0.1"


def _llm_params() -> dict[str, float]:
    """Generation-side sampling params, read per call so tests can drive them via env."""
    return {
        "temperature": float(os.environ.get("LIF_ADVISOR_LLM_TEMPERATURE", _LLM_TEMPERATURE_DEFAULT)),
        "top_p": float(os.environ.get("LIF_ADVISOR_LLM_TOP_P", "1.0")),
        "presence_penalty": float(os.environ.get("LIF_ADVISOR_LLM_PRESENCE_PENALTY", "0")),
        "frequency_penalty": float(os.environ.get("LIF_ADVISOR_LLM_FREQUENCY_PENALTY", "0")),
    }
```

Apply at both sites:

| Site | Line | Today | Becomes |
|---|---|---|---|
| Agent model (`create_agent_with_memory`) | :123 | `temperature=0.0` | `**_llm_params()` |
| Reframer model (`reframe_query_with_identifiers`) | :259 | *(nothing → server default 1.0)* | `**_llm_params()` |

Defaults rationale (revised after live validation, `advisor-api.md` Part A) — **this plan does not select the temperature value**; what follows is only what the measurements support. Identifier/type/format fidelity was perfect at *every* temperature tested including 1.0, so the change is justified by **consistency/reproducibility**, not correctness safety — lower risk than originally framed. Measured reframer output stability (mean pairwise Jaccard) improves monotonically as temperature drops: 0.750 @ 1.0 → 0.831 @ 0.7 → 0.844 @ 0.3 → 0.888 @ 0.1 → 0.929 @ 0.0. That argues for pinning *one* value at both sites; it does not say which, and it is not an end-to-end measurement (see Caveat). Settled: `top_p=1.0`, penalties `0`, and a single shared value across both sites — splitting would need two env pairs for negligible benefit. Open: the temperature number.

**Caveat added 2026-09-01:** the above argues from Part A (reframer self-consistency) only. Part B, the one end-to-end retrieval measurement, does **not** support `0.1`: it ties `@1.0` on four of five queries and is materially worse on the fifth (advising session, rank 8 → 49). So the stability numbers justify making the value configurable and shared; they do not select `0.1`. Treat `0.1` here as a placeholder until re-measured.

Note: the two `ChatOpenAI` lines carry **different** ignore codes today — `# ty: ignore[unknown-argument]` at `:123` and `# ty: ignore[invalid-argument-type]` at `:259`. Keep each line's own code rather than copying one onto the other: pre-commit runs `ty check --error-on-warning`, so an ignore that stops matching becomes a hard failure.

### A2. Deployment wiring (env passthrough only)

| File | Anchor |
|---|---|
| `development/docker-compose.yml` | advisor-api environment block :177–182 |
| `development/advisor-demo-1org/docker-compose.yml` | :128–133 |
| `development/advisor-demo-3orgs/docker-compose.yml` | :249–254 |
| `deployments/advisor-demo-docker/docker-compose.yml` | :421–426 |
| `cloudformation/lif-advisor-api-taskdef-includes.yml` | after `LIF_ADVISOR_LLM_MODEL_NAME` :10 |
| `development/scripts/run_lif_advisor_restapi.sh` | exports :11 |

**Do not write a numeric temperature into these surfaces until the default is chosen** (Open questions). Committing today's placeholder to six files would recreate precisely the drift documented at `advisor-api.md:162`, where the Python fallbacks `384`/`128` match no deployed value. Either land A2 once the default is settled, or land it now for `_TOP_P` / `_PRESENCE_PENALTY` / `_FREQUENCY_PENALTY` only and add temperature after.

The form differs by surface — the shell script is not like the others:

| Surface | Form |
|---|---|
| the four compose files | `LIF_ADVISOR_LLM_TEMPERATURE: ${LIF_ADVISOR_LLM_TEMPERATURE:-<chosen>}`, mirroring neighboring entries |
| `cloudformation/lif-advisor-api-taskdef-includes.yml` | `- Name: LIF_ADVISOR_LLM_TEMPERATURE` / `Value: "<chosen>"`, mirroring `LIF_ADVISOR_MESSAGES_TO_KEEP` (:12–13) |
| `development/scripts/run_lif_advisor_restapi.sh` | `export LIF_ADVISOR_LLM_TEMPERATURE=${LIF_ADVISOR_LLM_TEMPERATURE:-<chosen>}` — **not** the unconditional `export VAR=value` its neighbors at :10–15 use, which would clobber an operator-set value and defeat the smoke test at Verification step 3 |

### A3. Tests

- New unit tests in `test/components/lif/langchain_agent/test_core.py` (currently a stub) covering `_llm_params()`: the fallbacks when nothing is set, the parsed values when set, and that both `ChatOpenAI` sites receive the same dict. Wrap the call in `patch.dict(os.environ, {...})` — the pattern at `test/components/lif/lif_schema_config/test_core.py:61-75`, which works there because `from_environment()` reads env at call time.
- This is why A1 uses a helper rather than module constants. Against import-time constants these tests would assert the import-time value no matter what the env var says: green, and proving nothing.
- No live-LLM assertions (offline CI).

### A4. Docs

- Update env-var tables in `docs/design/adr/ai_architecture/0001-ai-architecture-overview.md` (~:320).
- Findings live in [`advisor-api.md`](../../design/components/advisor-api.md) (already committed on this branch); this PR's doc edits link there and record the chosen defaults.

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
k=200 can drop toward 150 (advisor-api.md rec R3). **Decided: gets its own GitHub issue** — #715 is labeled Advisor API and this lives in semantic_search_service.

## Follow-up candidates — Change Set C sketch (not in this PR)

Maps to advisor-api.md finding F7 / rec R7: reframing helps vague queries hugely (skills 50→17, relocate 87→43) but regresses strong-signal ones whose raw wording already matches schema language (advising session 1→49). Candidate designs, in rough preference order:

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

## Open questions

Resolved 2026-08-23 unless marked otherwise. **One was reopened 2026-09-01** — the temperature default.

- ~~Final resting place for the findings write-up?~~ → [`advisor-api.md`](../../design/components/advisor-api.md).
- ~~Defaults temp `0.1` shared vs split agent/reframer values?~~ → Single shared value. **The default value itself is reopened (2026-09-01):** Part B shows no end-to-end benefit at `0.1` and one regression, so pick it when the sweep is rebuilt and committed (advisor-api.md R1/R3).
- ~~Does Change Set B need its own GH issue given the label mismatch?~~ → Yes, its own issue.

Remaining pre-PR work: implement Change Set A (+ rider), open the Set B issue.
