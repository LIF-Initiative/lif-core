# Issue #715 — SPIKE PR summary (draft)

Suggested title: `Issue #715: Advisor LLM-tuning spike — findings + Advisor component doc`
Refs #715 · Docs-only PR (code changes to follow as separate PRs)

---

## What this spike did

- **Config audit** of every LLM invocation surface in the Advisor path (retrieval TOP_K, both ChatOpenAI call sites, penalties, memory knobs).
- **Offline retrieval experiment** replicating the production pipeline exactly (MDR OpenAPI → schema leaves → `all-MiniLM-L6-v2` embeddings → cosine ranking; 15 realistic queries, 53-leaf gold set).
- **Live OpenAI validation** (gpt-4.1-mini, ~155 calls ≈ pennies): 125-call temperature sweep on the exact production reframer prompt + end-to-end reframer-vs-retrieval test.

## Headline findings

1. **k=200 is "return everything."** Index is now 247 leaves (Person 186 — the old "137 attributes" note is stale). Recall@200 = 92.5%, but that's 81% of the whole index per query; ranking stops filtering past k≈150.
2. **25–30% of top-k slots are wasted** by truncate-before-filter ordering (`semantic_search_service/core.py:396` slices before :416 filters out non-queryable reference-data roots).
3. **Description quality is the real ceiling, not TOP_K.** 90% of rank-151+ gold leaves have boilerplate descriptions (`informationSource*`, "primary key identifier"); e.g. `PositionPreferences.Relocation.*` never says "relocation," so its gold leaf ranks #87 with negative similarity.
4. **The reframer's temp-1.0 default was a reproducibility bug, not a correctness one.** Live tests (n=25/temp) showed identifier/format fidelity was perfect at *every* temperature including 1.0 — but output stability climbs as temp drops (mean pairwise Jaccard 0.750 @1.0 → 0.888 @0.1). Agent runs hardcoded 0.0 while reframer effectively ran 1.0.
5. **Reframing is query-dependent.** Real LLM synonym expansion hugely helps vague queries (skills 50→17, relocate 87→43 best-gold-rank) but can wreck strong-signal ones whose raw wording already matches schema language (advising-session 1→49); temperature flipped that borderline case (8↔49), so reframer variance becomes retrieval variance.
6. Even T=0 isn't deterministic (observed min pairwise Jaccard 0.814).

## Proposed follow-on changes

- **Set A (this issue, next PR):** env-configurable `LIF_ADVISOR_LLM_TEMPERATURE/_TOP_P/_PRESENCE_PENALTY/_FREQUENCY_PENALTY` at both ChatOpenAI sites; single shared value across both sites, justified by consistency/reproducibility; the default itself is an open question (Part B shows no end-to-end gain at `0.1` and one regression). Deployment wiring + offline unit tests.
- **Set B (own issue):** filter reference-data paths *before* top_k truncation in `semantic_search_service` (label mismatch keeps it off #715); then re-run the sweep and consider k→150.
- **Cleanup rider:** drop nonexistent `Organization` root from defaults (startup ERROR noise).
- **Follow-up tickets:** embed `json_path + description`; enrich boilerplate MDR descriptions; tame the regression tail via dual-query fusion / constrained reframer prompt / skip-expansion-when-schema-vocabulary.

## What this PR contains (docs only)

- New `docs/design/components/advisor.md` — first component doc for advisor-api; carries the full study (inventory tables, measured baselines, findings F1–F8, recommendations R1–R7).
- `docs/design/components/README.md` file-map row + `docs/INDEX.md` entry; cspell additions (`reframer`, `Jaccard`, `dedup`).
- No behavior changes. Raw experiment scripts/results archived locally under gitignored `.claude/plans/artifacts/`.

## Decisions made during the spike

- Single shared temperature value, not split agent/reframer. The default value is reopened as of 2026-09-01.
- Findings live in `design/components/` (Advisor was the missing per-service doc) rather than a new ADR.
- Set B gets its own GitHub issue.
