# Issue #1160 — Advisor LLM context budget stack: enforce the summary cap

Make the Advisor's LLM context budgets coherent as a stack: real summaries can no longer
exceed `LIF_ADVISOR_MAX_SUMMARY_SIZE` without limit, and a summary — however large — cannot
silently crowd retained messages out of the model input.

---

## Context: what the issue described vs. the code on main

The issue's described failure mechanism was written against the unmerged #212 trimming design:

1. langmem's `SummarizationNode` does **not** enforce `max_summary_tokens` — it is budget
   estimation only.
2. The summary was emitted as a `SystemMessage` and a post-summarization
   `trim_messages(strategy="last", include_system=True)` always kept it, giving it first claim on
   the `LIF_ADVISOR_TRIMMED_MESSAGES_SIZE` budget.
3. If a real summary reached that budget, the trimmed list collapsed to `[summary]` alone, and
   the latest human message + in-flight tool results were silently dropped.

On current `main` (HEAD `66fad9c`) points 2–3 no longer hold: #1163 (the #1162 fix) rewrote
`memory.py` and removed the `trim_messages` / `_safe_trim_messages` step entirely. The retained
tail is always prepended to the summary, so nothing is silently dropped anymore.

What **still** held was point 1: `create_summarization_node` passed the unbound model to
`SummarizationNode`, so `max_summary_tokens` was budget estimation only and real summaries could
exceed `LIF_ADVISOR_MAX_SUMMARY_SIZE` by an unbounded amount.

## Decision (confirmed with product/user)

- Enforce the summary cap at generation time via `model.bind(max_tokens=...)`.
- Leave `LIF_ADVISOR_TRIMMED_MESSAGES_SIZE` **in place** (code + deployments), even though
  nothing reads it — no deployment-artifact churn this iteration.
- Do **not** resurrect a post-summarization trim.

The resulting coherent operating stack (deployed: taskdef 2048/1024/384):
`MAX_CONVERSATION_SIZE` = token trigger for summarization (2048), `MAX_SUMMARY_SIZE` = enforced
summary cap (1024), `MESSAGES_TO_KEEP` = retained tail (4).

## Implementation

`components/lif/langchain_agent/memory.py` — `create_summarization_node()`:

```python
return SummarizationNode(
    token_counter=count_tokens_approximately,
    model=model.bind(max_tokens=max_summary_size),
    max_tokens=max_conversation_size,
    max_summary_tokens=max_summary_size,
    input_messages_key="summary_input_messages",
    output_messages_key="summary_output_messages",
)
```

Per langmem 0.0.27, `max_summary_tokens` is explicitly not passed to the summary LLM
(`summarization.py:383-386, 705-708`): "If you want to enforce it, you would need to pass
`model.bind(max_tokens=max_summary_tokens)`". Binding returns a new runnable, so the main
agent model passed to `create_react_agent` in `core.py` is unaffected.

## Tests

`test/components/lif/langchain_agent/test_memory.py`:

- `test_summarizer_enforces_summary_token_cap` — the returned node's model is
  `model.bind(max_tokens=max_summary_size)` and `max_summary_tokens` is wired through.
  Regression for "summaries can exceed the cap unboundedly".
- `test_oversized_summary_cannot_crowd_out_retained_messages` — a ~200k-token summary still
  leaves the full retained tail in `llm_input_messages`; the model input can never collapse to
  the summary alone. Regression for the issue's headline concern in current-code terms.

## Verification

- `uv run pytest test/components/lif/langchain_agent/` — 8 passed (2 new).
- `uv run pytest test/.../langchain_agent/ test/bases/lif/advisor_restapi/` — 27 passed.
- `uv run ruff check` / `ruff format --check` / `ty check` — clean.
- `uv run pre-commit run --files <memory.py, test_memory.py>` — all hooks passed.

## Out of scope

Retiring `LIF_ADVISOR_TRIMMED_MESSAGES_SIZE` from code/deployments; aligning code defaults
(`384/128/384`) with deployment values (`2048/1024`); reintroducing post-summarization
trimming. Resolving the dead knob is deferred per explicit user decision.