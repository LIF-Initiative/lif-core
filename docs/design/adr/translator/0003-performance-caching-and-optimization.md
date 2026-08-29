# ADR 0003: Performance — Caching and Optimization

Date: 2026-08-29

## Status

Proposed

## Context

Issue #722 identifies performance bottlenecks in the Translator component. Every
request currently:

1. Makes HTTP round-trips to the MDR (source schema, target schema,
   transformation mappings). ADR 0001 acknowledged this trade-off when choosing
   runtime fetching over pre-initialization, noting "this may slow the
   performance of the translator if this data is not cached."
2. Performs N+1 `jsonschema.validate()` calls per request (one tentative
   validation after each of N mapping merges, plus one final validation).
3. Executes an extra `deepcopy` per mapping merge to support rollback when a
   fragment violates the target schema at the point of merge.
4. Re-parses JSONata expression strings from scratch on every `run()` call.

No performance benchmarks, load tests, or profiling infrastructure existed
prior to this work. Note that #1158 subsequently instrumented the merge loop
with stage timings and applied/discarded counters; this ADR builds on that
baseline.

## Decision

### 1. MDR Response Caching

Add an in-memory TTL cache (`cachetools.TTLCache`) for MDR-fetched **schemas
only** (source and target). Cache TTL is configurable via the
`TRANSLATOR_CACHE_TTL_SECONDS` environment variable, defaulting to 300 seconds
(5 minutes).

**Transformations are deliberately NOT cached.** The MDR transformation endpoint
returns no version/ETag the translator could use to invalidate a cache, so an
edit — an updated expression, or an imported/hand-edited group — would otherwise
be hidden until TTL expiry, violating ADR 0001's live-MDR guarantee that edits
are reflected on the very next translation (enforced by the
`test_update_transform_only_expression` and
`test_import_hand_edited_group_then_translate_reflects_all_changes` tests).

Cache keys include the `tenant_schema` parameter to ensure correctness in
multi-tenant deployments. Process-local only — no shared or distributed cache.

### 2. Merge / Rollback Pattern

Keep the per-fragment "tentative merge, validate, commit or rollback" pattern
already shipped in #1158: copy the accumulated result, merge the fragment into
the copy, validate the copy, and either commit it or discard the fragment. One
`deepcopy` per fragment is the minimum required to support rollback, and the
fragment copy inside `deep_merge` is to avoid mutating the mapping's output.

When intermediate validation is disabled (see below), rollback is impossible by
definition, so the per-fragment `deepcopy` is skipped entirely and each fragment
is merged in place — the final validation is the sole gate.

### 3. Configurable Intermediate Validation

Add a `validate_intermediately` flag to `BaseTranslatorConfig` (default `True`).
When `True`, the translator validates the accumulated result against the target
schema after each fragment merge (current behavior). When `False`, intermediate
validation is skipped — along with the per-fragment rollback copy — and only the
final validation runs.

Default `True` preserves the safe, existing behavior. Callers prioritizing
throughput over early error detection can set it to `False`.

### 4. JSONata Expression Caching

Cache compiled `jsonata.Jsonata` objects keyed by expression string. The cache is
**thread-local** because a `Jsonata` instance binds the input document into its
own evaluation environment on each `evaluate()` call (`exec_env.bind("$", input)`),
so a single shared instance is not safe for concurrent use across threads. The
library itself uses the same thread-local pattern for its parser. A thread-local
cache is bounded by the number of distinct expressions seen per thread, which in
practice is a small fixed set.

## Alternatives Considered

- **Redis or shared cache**: Adds operational complexity (deployment, connection
  management, serialization overhead). Rejected for now. Revisit if multi-worker
  shared caching becomes a concrete requirement.
- **Remove per-fragment validation entirely**: Sacrifices early error detection
  and provides less useful diagnostics when invalid fragments are produced.
  Kept as an opt-out rather than removed.
- **Process-shared compiled JSONata cache**: A `TTLCache` shared across threads
  risks a race on the instance's evaluation environment (see above). Rejected in
  favor of the thread-local cache, which is safe and nearly as effective.
- **Batch/streaming translation**: Deferred to future roadmap per the design
  doc. The component's design anticipates streaming as an extension, not a
  redesign.
- **Pre-initialized translator with schemas at startup**: Would eliminate
  runtime MDR calls entirely but conflicts with ADR 0001's decision to ensure
  live integration with MDR for constantly changing schemas and mappings.

## Consequences

- **Staleness window (schemas only)**: Cached schemas may be stale for up to
  `TRANSLATOR_CACHE_TTL_SECONDS` (default 300s). Acceptable because schema
  definitions change infrequently in production and no correctness test depends
  on immediate schema reflection. Transformations are not cached, so mapping
  edits always take effect on the next translation.
- **Transformation fetch cost remains**: Every translation still performs one
  MDR round-trip for the transformation mappings (2 of the original 3 round-trips
  — the two schemas — are served from cache). This is the price of the live-edit
  guarantee and is the same behavior as before this ADR.
- **Cold start**: The schema cache is empty after restart. First request per
  schema pair incurs schema MDR latency; subsequent requests within the TTL
  window are served from cache.
- **`validate_intermediately=False` trade-off**: Sacrifices early error detection
  and per-fragment diagnostics (and rollback) for speed. Callers must understand
  this trade-off.
- **Memory overhead**: The schema TTLCache is bounded at 128 entries; each entry
  holds a JSON dict, so memory impact is negligible.
  The JSONata cache is per-thread and bounded by distinct expression strings.
- **New dependency**: `cachetools` (~6.1), a pure-Python library with no native
  dependencies.

## References

- [#722: Investigate and Improve Translator Performance](https://github.com/LIF-Initiative/lif-core/issues/722)
- [ADR 0001: Initialization vs MDR Dependency](./0001-initialization-vs-mdr-dependency.md)
- [Translator Design Doc — Performance Section](../../design/components/translator.md#performance)