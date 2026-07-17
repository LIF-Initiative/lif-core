# Advisor: end-to-end LLM response streaming

**Status:** Proposed
**Date:** 2026-06-02
**Author:** bjagg
**Tracking issue:** [#970](https://github.com/LIF-Initiative/lif-core/issues/970)

> Stream the LIF Advisor's answers token-by-token from the LangGraph agent through the API to the chat UI, replacing the current single buffered response — including the backend concurrency fix that streaming makes mandatory.

## Problem

The Advisor returns each answer as a single buffered response: the UI shows a typing indicator until the entire reply is ready, then drops it in at once. For multi-second answers (the agent makes several LLM + tool calls per turn) this feels slow and unresponsive. We want to stream tokens to the UI as they are generated.

This consolidates the previously-scattered streaming/async tickets ([#422](https://github.com/LIF-Initiative/lif-core/issues/422) closed as dup, [#75](https://github.com/LIF-Initiative/lif-core/issues/75) async, the closed #144).

## Why this is more than "wire up a stream"

A design pass across the agent, API, frontend, and deployment layers surfaced three issues that would otherwise make streaming *appear* to work locally but break or regress in the deployed (demo) environment. These are in scope for #970:

1. **Shared ALB `idle_timeout = 30s`** (`cloudformation/service-common.yml:338`). The ALB idle timeout measures the gap *between bytes*, not total duration. Once tokens flush every few hundred ms the clock keeps resetting, so a long stream survives — **but** if time-to-first-token (reframe + first tool calls) exceeds 30s, the ALB drops the connection *before the first chunk*, producing intermittent failures. Mitigations below (immediate `start` chunk + raise the timeout).
2. **`reframe_query_with_identifiers` is a synchronous `llm.invoke`** (`components/lif/langchain_agent/core.py:266`) running on a **single uvicorn worker** (`projects/lif_advisor_api/Dockerfile2:49`, `MinCount/MaxCount=1`). Today this is hidden; under streaming a blocking call **stalls the event loop and every concurrent stream**. This is a pre-existing latent concurrency bug that streaming promotes to critical — fixing it (make async or `run_in_threadpool`) is part of this work.
3. **`fetch` bypasses the axios auth interceptor.** The streaming client must use `fetch` (not axios), so the 401→refresh→retry logic in `frontends/lif_advisor_app/src/utils/axios.ts:25-51` does not apply. We must share the refresh logic between the interceptor and the fetch path.

## Wire protocol: NDJSON

**Decision: newline-delimited JSON (`application/x-ndjson`)**, one JSON object per line, discriminated by a `type` field. Rejected SSE (`text/event-stream`): `EventSource` cannot send an `Authorization` header (our auth is header-based JWT), so SSE would require a `fetch` reader anyway, keeping its heavier framing while losing its only advantage.

```
{"type": "start"}                                                  # exactly 1, first — see ALB note
{"type": "token", "content": "partial text "}                      # 0..N
{"type": "final", "content": "<full assembled text>", "tokens": 1234, "cost": 0.0123}  # terminal
{"type": "error", "message": "...", "code": "agent_error"}          # terminal, replaces `final`
```

Contract rules:
- `final.content` is the **full** assembled message (not a delta), so a client that ignored token chunks still gets a complete answer — preserving backward-compatible semantics and giving the UI one place to read `tokens`/`cost`.
- Exactly one of `final` | `error` terminates the stream. Once `StreamingResponse` starts, the HTTP status is already `200`, so **mid-stream failures must be signaled in-band** via an `error` chunk, not an HTTP code.
- The `start` chunk is emitted immediately on entering the generator, before reframe/tool work, to reset the ALB idle clock (see risk #1).

## Architecture by layer

### 1. Agent layer — `components/lif/langchain_agent/core.py`

Add a streaming sibling to `ask_agent`; keep `ask_agent` for the non-streaming `save_interaction_summary` (logout) path.

```python
async def ask_agent_stream(self, task: str, message: str) -> AsyncIterator[dict]:
    """Yields {"type":"token","content":...} chunks, then exactly one
    {"type":"final","content":full,"tokens":N,"cost":C} (or {"type":"error",...})."""
```

- Build the model with `streaming=True, stream_usage=True` (`create_agent_with_memory`); consume `agent.astream_events(..., version="v2")`. The two flags are independent: `streaming=True` turns on token-by-token emission, while `stream_usage=True` attaches token-usage metadata to those streamed chunks — needed so the token/cost tally (below) can be built from the stream itself rather than a separate accounting call.
- Surface only the user-facing turn. Under `astream_events` the graph emits token-stream events from *several* internal LLM calls — the `pre_model_hook` summarization, tool-planning, and the actual answer — all interleaved. We forward only the answer's tokens by keeping events that are **both** `event["event"] == "on_chat_model_stream"` **and** (guarded) `(event.get("metadata") or {}).get("langgraph_node") == "agent"`. The `langgraph_node == "agent"` check is load-bearing: without it, summarization and tool-planning tokens leak into the user's visible stream.
- **Reframe** stays a separate, non-streamed call that runs first (its tokens/cost fold into the final tally) — but is made **non-blocking** (see risk #2). It adds the dominant time-to-first-token latency.
- **Token/cost:** aggregate the agent-node `on_chat_model_end` messages and run them through the existing `calculate_tokens_and_cost` + `LLM_TOKEN_COSTS` (`core.py:236-264`). Do **not** use a provider-locked `get_openai_callback`.
- `pre_model_hook`/summarization and `InMemorySaver` checkpointing still fire under `astream_events` (same graph execution). Only assign `self.messages` on success; always terminate the generator with a `final` or `error` chunk (never raise out of it) so the API layer can close the stream cleanly.

### 2. API layer — `bases/lif/advisor_restapi/core.py`

Convert `/start-conversation` and `/continue-conversation` to `fastapi.responses.StreamingResponse` consuming the agent generator through a small `_ndjson_relay` that JSON-encodes each chunk and emits an in-band `error` chunk on exception.

- Compose with the session-restore work (#972 / PR #978): call `_ensure_user_session(username)`; the idempotent "welcome back" and rehydration paths emit a **single `final` chunk** (a one-element stream) so the client reader stays uniform.
- `Depends(get_current_user)` resolves **before** streaming starts, so a 401 is still a normal JSON error with the right status — auth failures never enter the in-band-error path.
- `response_model=ChatMessage` is ignored for `Response` subclasses at runtime; document the real NDJSON contract via a `responses={200: {"content": {"application/x-ndjson": ...}}}` override so `/docs` stays honest.
- Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`. (Defensive — there is no nginx/proxy buffering the API today; the ALB does not buffer bodies. Correct if an intermediary is added later.)

### 3. Frontend — `frontends/lif_advisor_app/`

New `src/utils/streaming.ts`: a `fetch().body.getReader()` + `TextDecoder` async generator with correct partial-line buffering (keep the trailing incomplete line; flush the remainder at end), **guarded** per-line `JSON.parse` (a malformed line is dropped, not fatal), and `reader.cancel()` in a `finally` so abort/early-exit releases the connection.

> **On dropping a malformed line:** it loses only that one mid-stream `token` *delta*, not the answer. The terminal `final` chunk carries the full assembled `final.content` (per the contract above), so the complete text still renders at end-of-stream — the display self-heals rather than staying permanently short a chunk. The only content-losing case is a malformed `final`/`error` line itself, which surfaces as a stream error (the generator never sees a terminal chunk), not as silently-missing text.

Rework `src/hooks/useChat.ts` to consume it: append `token` deltas into the existing typing-placeholder bot message, capture `tokens`/`cost` from `final`, render `error` gracefully.

- **Abort:** thread an `AbortController` `signal` into the `fetch` (the load-bearing line); store the controller in a `useRef` and abort on a new send / unmount.
- **Auth (the hard part):** extract a shared `refreshAccessToken()` from `axios.ts` used by *both* the interceptor and the fetch path (no duplicated refresh logic); on a pre-stream 401, refresh once and retry the fetch. Use this app's real localStorage keys (`token` / `refreshToken`) and `VITE_LIF_ADVISOR_API_URL`.
- **Option-button interplay (#971 / PR #982):** `extractOptions` already parses only a *trailing run* of complete `<<...>>` markers and strips them from displayed text every frame, so raw markers never flash mid-stream. Defer rendering the option *buttons* until the `final` chunk via an `isStreaming` gate (avoids partial-pair flicker like `Yes` then `Yes, No`).

## Rollout: content negotiation, not twin flags

The frontend Vite flag is **build-time only** — Vite reads `VITE_*` env vars during `npm run build` and compiles each value into the static JS bundle as a literal constant, so it can't be changed after the build without rebuilding the bundle. That makes a frontend flag which must stay in lockstep with a backend flag painful to operate. Instead:

- Backend `LIF_ADVISOR_STREAMING` env (default off). Toggling it is a **config change, not an image rebuild**: edit the value in the ECS task definition and redeploy. That is a new task-def revision plus a rolling task restart — a brief rollout, *not* zero-downtime — but with no image rebuild and no code change, which is the win over the build-time frontend flag.
- The frontend sends `Accept: application/x-ndjson`; the reader branches on the response `Content-Type`. An old frontend + new backend stays safe automatically; an old backend + new frontend falls back to the buffered path.
- The backend streams only when `LIF_ADVISOR_STREAMING=true` **and** the `Accept` header is present; otherwise it returns today's `ChatMessage` JSON.

Rollback = flip the backend env off (no image rebuild — the same task-def-revision + rolling-restart as above, on the order of a normal ECS redeploy). Keep the legacy axios path in `useChat.ts` until streaming is proven in demo. Verify on `*.dev.lif.unicon.net` with a multi-minute conversation (to exercise the 30s ALB window) before promoting pinned tags to demo.

## Deployment changes

- **Raise the shared ALB `idle_timeout`** (`cloudformation/service-common.yml:338`) from 30s to ~120s. This is a single global knob shared by all services — low-risk and broadly beneficial, but call it out explicitly in the PR.
- Emit the `start` chunk immediately (above) as belt-and-suspenders for time-to-first-token.

## Testing

- **Agent generator:** mock `agent.astream_events` to yield a scripted event sequence; assert token order, the single terminal chunk, and that tokens/cost include the reframe contribution. (`test/components/lif/langchain_agent/`)
- **API:** `httpx.AsyncClient` + `ASGITransport`, `async with client.stream(...)` over `aiter_lines()`; assert NDJSON parses, terminal chunk carries tokens/cost, flag-off returns the legacy `ChatMessage`, and auth is still enforced. (`test/bases/lif/advisor_restapi/test_core.py` — coordinate with #978's additions.)
- **Frontend reader:** vitest (harness added by PR #982) with a mock `ReadableStream` — cover mid-line chunk splits, a malformed line (dropped), no-trailing-newline flush, token→final assembly, error chunk, non-2xx throwing a typed error, and abort calling `reader.cancel()`. (`src/utils/streaming.test.ts`)
- **Integration:** add `integration_tests/test_07_advisor_stream.py` (respecting `--skip-unavailable`) — the only test that catches the ALB-buffering/idle class against a deployment-like stack.

## Observability

Log per stream: **time-to-first-token** (the early-warning for the ALB-idle problem), total duration, total tokens/cost (move the existing `Response:` log to the terminal chunk), and distinguish client aborts (`CancelledError` / `ClientDisconnect`) from agent errors. Tag with `username` / `thread_id`.

## Sequencing — #970 lands last

#970 touches `langchain_agent/core.py`, `advisor_restapi/core.py`, `useChat.ts` and adds `streaming.ts`. Three PRs are in flight on the same files; merge order:

1. **[#975](https://github.com/LIF-Initiative/lif-core/pull/975)** (dead-code) — semantic dependency: build the streaming generator on the post-#975 `langchain_agent/core.py` (it removes the already-broken `summarize_conversation`).
2. **[#978](https://github.com/LIF-Initiative/lif-core/pull/978)** (session restore) — biggest collision: it rewrites the same two handlers and `test_core.py` and adds `_ensure_user_session`, which the streaming endpoints call. Do **not** develop #970 and #978 in parallel on these handlers.
3. **[#982](https://github.com/LIF-Initiative/lif-core/pull/982)** (option buttons) — provides the vitest harness the frontend tests need, and touches `useChat.ts` + the chat components the `isStreaming` gate extends.
4. **#970** — rebase on all three. Expect mechanical conflicts in `useChat.ts` and an `axios.ts` interceptor refactor layered on #972's null-guard.

## Open decisions

1. **ALB idle timeout** — raise the shared knob to ~120s (recommended) vs. rely solely on the immediate `start`-chunk keepalive.
2. **Reframe fix scope** — fix the blocking `llm.invoke` inside #970 (recommended) vs. split as a standalone precursor PR (it's an independently shippable latent bug).
3. **Final-usage source** — aggregate `on_chat_model_end` agent-node messages (recommended, no extra round-trip) vs. LangGraph's `aget_state` (the async `get_state`) to read the final assembled messages, mirroring how `ask_agent` reads `ainvoke`'s result.

## Out of scope / related

- httpOnly - cookie auth migration ([#977](https://github.com/LIF-Initiative/lif-core/issues/977)) — if adopted, the fetch auth approach above changes (cookies ride automatically).
- `<<...>>` marker hygiene in saved summaries ([#983](https://github.com/LIF-Initiative/lif-core/issues/983)).
- Multi-instance scaling — blocked by the in-memory `conversation_states` / `InMemorySaver`; demo is `MinCount=1`. Out of scope here.
