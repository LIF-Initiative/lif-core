# Issue #179 — Reduce MongoDB calls in the LIF Query Cache write path

Reduce the number of round trips made to MongoDB by the LIF Query Cache service,
picking up Copilot's recommendations from the original #129 write-capability work
(then tracked as LIFCORE-62). The change is contained to the **write** operations
(`add`, `update`); the read path (`query`) is already a single `find`.

> **Scope note.** The original Copilot comment thread is not present in current git
> history (it predates this repo's git import and lives in the old tracking system).
> This plan is derived by reading the current code in
> `components/lif/query_cache_service/core.py` rather than from that specific note.
> The reductions proposed here are the ones that are safely achievable in the current
> code and preserve behavior.

---

## Current state & call-count analysis

All write-path logic lives in `components/lif/query_cache_service/core.py` (async,
MongoDB via a module-level `collection`). Today:

| Function | Line | MongoDB calls today | Worst/common-case note |
|----------|------|--------------------:|------------------------|
| `query()` | `139` | **1** | `find` only — already optimal. |
| `add()` | `263` | **2** | `insert_one` **+** redundant `find_one` refetch. |
| `update()` | `178` | **2–4** | `find_one` (array check), `update_one` (array init), `update_one` (main), `find_one` (result). |
| `save()` | `288` | **2** | `find` (load record) **+** `update_one` upsert. |

### `update()` breakdown
| # | Line | Call | When |
|---|------|------|------|
| 1 | `210` | `find_one` (inspect current doc) | only when `$push` ops exist |
| 2 | `229` | `update_one` (array inits) | only when a push target isn't already a list |
| 3 | `245` | `update_one` (main update) | always |
| 4 | `248` *(before change)* | `find_one` (fetch result to return) | always |

So even the simplest `$set`-only update makes **2** calls (write + result fetch).

---

## Proposed changes

### 1. `add()` — 2 → **1** call
`core.py:263`. After `insert_one(lif_record.model_dump(by_alias=True))`, the current
code does a redundant `find_one({"_id": inserted_id})` before building the returned
`LIFRecord`. This refetch is **dead weight**:

- `LIFRecord` (`datatypes/core.py:61`) has **no `_id` field**, so the `_id` from Mongo is
  discarded on construction (`LIFRecord(**added_record)` ignores it).
- The inserted document is *literally* the input `lif_record` aliased to PascalCase — the
  same data we already hold.
- `field_validator`/`ConfigDict` aliasing (`person` ↔ `Person`) round-trips on the input.

**Change:** drop the `find_one`; return the input `lif_record` directly when
`inserted_id` is truthy. Resource-not-found behavior (no inserted ID) is unchanged.

### 2. `update()` — merge final write + result fetch; common case 2 → **1** call
`core.py:178`. Replace the final `{ update_one + find_one }` pair with a single
**`find_one_and_update`** using `projection={Person:1, _id:0}` and
`return_document=pymongo.ReturnDocument.AFTER`:

```python
doc = await collection.find_one_and_update(
    mongo_filter,
    update_doc,
    projection={PERSON_KEY_PASCAL: 1, "_id": 0},
    return_document=ReturnDocument.AFTER,
)

if doc and PERSON_KEY_PASCAL in doc:
    return LIFRecord(person=doc[PERSON_KEY_PASCAL])  # ty: ignore[unknown-argument]
raise ResourceNotFoundException(...)
```

**Behavior parity:**
- Match → `find_one_and_update` returns the post-update doc with only `Person` projected,
  identical to the old `find_one`.
- No match → `find_one_and_update` (non-upsert) returns `None`, which then raises the
  same `ResourceNotFoundException("No matching record after update…")` the old
  `find_one` path raised.

**Net effect on `update()`:** `$set`-only drops to **1** call; the array-init path drops
from 4 to ≤3. The array-init step (#1/#2) is **deliberately kept**: Mongo `$push` fails
against a non-array field, so missing arrays must be materialized first. This is genuine
work, not overhead.

### 3. `save()` — **no change**
`core.py:288` legitimately needs both calls. `save` composes incoming
`LIFFragment`s onto the existing record via `compose_with_fragment_list` (with
`replace_existing=True` per #1165), so it must **read** the current record before it can
know what to write, then upsert. `find_one_and_update` can't help here because the
composition happens client-side *between* the read and the write. Out of scope.

### 4. `query()` — **no change**
Already a single `find`. Out of scope.

---

## Summary of net effect

| Function | Now | After | Savings |
|----------|-----|-------|---------|
| `query()` | 1 | 1 | — |
| `add()` | 2 | **1** | −1 |
| `update()` worst case | 4 | ≤3 | −1 |
| `update()` common (`$set` only) | 2 | **1** | −1 |
| `save()` | 2 | 2 | — (needs both) |

---

## Files touched

- `components/lif/query_cache_service/core.py`
  - `add()` — drop redundant `find_one`; return input record.
  - `update()` — switch final `update_one`+`find_one` → `find_one_and_update`.
  - add `from pymongo import ReturnDocument` import.
  - `add()` docstring: drop the stale "with '_id' field included" wording.
- `test/components/lif/query_cache_service/test_core.py`
  - Was a placeholder (`test_sample`). Add mock-collection unit tests (see below).
- No changes to `bases/lif/query_cache_restapi/core.py` or any datatypes — the public
  function signatures and the `/add`, `/update`, `/save`, `/query` endpoints are
  unchanged.

---

## Test strategy

The module uses a module-level `collection` global, so tests patch `core.collection`
with a mock whose coroutine methods are `AsyncMock`s. Assert both **call counts** (the
actual point of #179) and **output equivalence**:

| Test | Asserts |
|------|---------|
| `add` happy path | `insert_one` awaited once with the alias dump; `find_one` **not** called; returns the input record. |
| `add` no inserted ID | raises `ResourceNotFoundException`; no `find_one`. |
| `update` `$set`-only | `find_one_and_update` called once; `update_one` and `find_one` **not** called; correct projection / `ReturnDocument.AFTER` / `$set` doc; correct returned `person`. |
| `update` with `$push` + missing array | `find_one`, `update_one` (array init), and `find_one_and_update` each fire once, in that order. |
| `update` no match | `find_one_and_update` returns `None` → raises `ResourceNotFoundException` (parity with old behavior). |

Call-count assertions are what make "fewer calls" enforced rather than claimed, and
would have caught a regression if the old `find_one`-pair were re-introduced.

---

## Validation performed

- `uv run pre-commit run --files <both files>` → **ruff check**, **ruff format**,
  **cspell**, **ty-check**, **pytest-test** all pass.
- `uv run pytest test/components/lif/query_cache_service test/bases/lif/query_cache_restapi
  test/bases/lif/query_cache_module test/components/lif/query_cache_read` → **9 passed**.
- New tests: **6 passed**.

---

## Open questions / decisions for the team

1. **Original Copilot recommendations.** The exact wording from the #129-era comment is
   not in current git history. If anyone has the original note, reconcile it against this
   plan — the reductions here are the subset that is safe in today's code.
2. **Is `save()`'s read+write acceptable?** It is genuinely two calls and out of scope
   here. A future optimization would require batching fragment composition or moving
   composition server-side inside a single update, which is a larger design change.
3. **Integration coverage.** `integration_tests/test_02_query_cache.py` exercises only
   `/query`. The write endpoints (`/add`, `/update`, `/save`) have no integration coverage.
   This PR adds unit coverage for call counts + equivalence; adding write-path integration
   tests would further harden it (potentially a follow-up).

---

## Out of scope

- `query()` / `save()` call-count reduction (rationale above).
- Any schema, datatype, or REST-layer changes.
- Behavior changes beyond the call-count reduction (outputs are kept equivalent).
- Frontend, deployment, or infra changes.
