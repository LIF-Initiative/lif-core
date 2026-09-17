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

### Measured baseline

`test/components/lif/translator/benchmark_core.py` establishes the baseline #722
asks for. Run it explicitly -- it is deliberately not named `test_*.py`, so a
directory scan will not collect it and pytest-benchmark's several-hundred
iterations per case stay out of every CI run:

    uv run pytest test/components/lif/translator/benchmark_core.py --benchmark-only

`BaseTranslator.run`, median, scaling with mapping count:

| mappings | median |
|---:|---:|
| 1 | 2.0 ms |
| 5 | 6.1 ms |
| 10 | 11.5 ms |
| 20 | 21.7 ms |
| 50 | 53.1 ms |

Roughly linear at ~1 ms per mapping. That is the number any future optimization
has to beat, and it is why sections 3 and 4 below were withdrawn rather than
tuned: neither had a measurement showing it moved this curve.

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

### 2. Merge / Rollback Pattern — unchanged

Keep the per-fragment "tentative merge, validate, commit or rollback" pattern
already shipped in #1158, exactly as it stands: copy the accumulated result,
merge the fragment into the copy, validate the copy, and either commit it or
discard the fragment. One `deepcopy` per fragment is the minimum required to
support rollback.

### 3. Not adopted: configurable intermediate validation

An earlier revision of this ADR proposed a `validate_intermediately` flag to skip
per-fragment validation and its rollback copy. Withdrawn during review: as
implemented it was unreachable from production — `Translator.run` never passed it
and `TranslatorConfig` had no field for it, so only the `/initialize` test harness
could set it. It would have shipped permanently disabled, adding a branch to the
hot path in exchange for nothing. Revisit only with a measurement showing the
per-fragment validation is actually a bottleneck, and with the flag wired through
`TranslatorConfig`.

### 4. Not adopted: JSONata expression caching

An earlier revision cached compiled `jsonata.Jsonata` objects keyed by expression
string. **Withdrawn during review as incorrect.**

`jsonata-python` resolves `$now()` and `$millis()` through
`Jsonata.CURRENT.jsonata.timestamp`, a class-level thread-local re-pointed **only
in `Jsonata.__init__`**, while `evaluate()` updates `self.timestamp`. Constructing
an instance per evaluation keeps those the same object, so the current code is
correct by construction. Caching the instances freezes `CURRENT` on whichever
expression was compiled last, and every other cached expression then emits a stale
timestamp. Reproduced: a cached `$millis()` mapping returned an identical value
across a 2-second gap (delta 0 ms) where the uncached path advanced 2001 ms.

No transformation in this repository currently uses `$now()` or `$millis()`, so
the defect was latent rather than active — but transformations are live-fetched
from MDR, so the repository is not the full population.

Two further problems, either of which would need solving independently:

- A cached instance retains a reference to the last document it evaluated
  (`environment.bindings["$"]`), so full learner payloads stay reachable in a
  long-lived cache across tenants. Verified directly.
- The cache was an unbounded plain dict keyed by expression string. Because
  transformations are live-fetched by design, every playground edit would add a
  permanent entry.

Any future attempt should re-point `Jsonata.CURRENT` per evaluation (or use a
library version that does), bound the cache the way the schema cache is bounded,
and carry a regression test that evaluates a `$millis()` mapping twice across a
sleep.

## Alternatives Considered

- **Redis or shared cache**: Adds operational complexity (deployment, connection
  management, serialization overhead). Rejected for now. Revisit if multi-worker
  shared caching becomes a concrete requirement.
- **Remove or make optional the per-fragment validation**: Sacrifices early error
  detection and per-fragment diagnostics. Not adopted -- see section 3.
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
- **Memory overhead**: The schema TTLCache is bounded at 128 entries; each entry
  holds a JSON dict, so memory impact is negligible.
- **New dependency**: `cachetools` (~6.1), a pure-Python library with no native
  dependencies.

## References

- [#722: Investigate and Improve Translator Performance](https://github.com/LIF-Initiative/lif-core/issues/722)
- [ADR 0001: Initialization vs MDR Dependency](./0001-initialization-vs-mdr-dependency.md)
- [Translator Design Doc — Performance Section](../../design/components/translator.md#performance)