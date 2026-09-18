# `lif_fragment_utils` — Component

Pure helpers for shaping `LIFFragment` lists. No I/O, no query-planner-specific
types — split out of `query_planner_service` so consumers that only need
fragment shaping don't have to pull in that brick's `httpx`-based service and
job-store logic.

## Public surface

```python
from lif.lif_fragment_utils import adjust_lif_fragments_for_initial_orchestrator_simplification
```

`adjust_lif_fragments_for_initial_orchestrator_simplification(lif_fragments, desired_fragment_paths)` takes a full-person fragment (`person.all`) plus a list of desired dotted paths, and returns one fragment per desired path.

## Layout

| File | Contents |
|---|---|
| `core.py` | `adjust_lif_fragments_for_initial_orchestrator_simplification` and its private case-insensitive key lookup helper |

## Used by
- `components/lif/query_planner_service` — shaping fragments before sending orchestration results to the LIF Cache
- `orchestrators/dagster/lif-orchestrator` (and the `dagster_*` deployment projects) — the translation step (`run_translation` in `lif_job.py`)
