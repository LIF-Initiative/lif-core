# Contractor PR Triage: PRs #813 and #817

**Author:** mryoho (contractor)
**Date reviewed:** 2026-02-20
**Status:** Recommend closing both PRs

## Background

A contractor (mryoho) submitted two PRs in late January 2026 attempting to centralize schema parsing and dynamic model generation from an A&M proof-of-concept codebase. The work was unfinished when the contractor's engagement ended. Since then, the team has independently built equivalent functionality via `openapi_schema_parser`, `semantic_search_service`, `schema_state_manager`, and `lif_schema_config`.

---

## PR #813: "328 Add `schema` and `dynamic_models` components"

- **Created:** 2026-01-27 | **Commits:** 4 | **Files:** 13
- **Branch:** `328-schema-and-dynamic-models-from-a-and-m`

### What it adds

| Component | Lines | Purpose |
|-----------|-------|---------|
| `components/lif/datatypes/schema.py` | 11 | `SchemaField` dataclass (json_path, description, attributes, py_field_name) |
| `components/lif/schema/core.py` | 144 | OpenAPI schema parsing: `extract_nodes()`, `resolve_openapi_root()`, `load_schema_nodes()` |
| `components/lif/dynamic_models/core.py` | 406 | Dynamic Pydantic model builder: filter, mutation, full variants from `SchemaField` lists |
| `string_utils/core.py` changes | ~20 | Improved `to_pascal_case` (acronym handling), `to_camel_case`, `safe_identifier` (underscore collapse) |
| Tests | ~1,400 | Comprehensive tests for all new components |
| `test/data/test_openapi_schema.json` | 71 | Test fixture |

### Overlap with existing code

| PR adds | Already exists | Location |
|---------|---------------|----------|
| `SchemaField` dataclass | `SchemaLeaf` (identical fields minus `py_field_name`) | `openapi_schema_parser/core.py` |
| `load_schema_nodes()` | `load_schema_leaves()` | `openapi_schema_parser/core.py` |
| `extract_nodes()` | `extract_leaves()` | `openapi_schema_parser/core.py` |
| `resolve_openapi_root()` | Same function, same logic | `openapi_schema_parser/core.py` |
| `build_dynamic_model()` (filter/mutation/full) | `build_dynamic_filter_model()` + `build_dynamic_mutation_model()` | `semantic_search_service/core.py` |
| Improved `to_pascal_case` / `to_camel_case` | Centralized in `lif_schema_config/naming.py` | `lif_schema_config/naming.py` |

The `schema_state_manager` component already orchestrates the full lifecycle: loads schema via `openapi_schema_parser`, builds models via `semantic_search_service`, and maintains a `SchemaState` with leaves, filter_models, mutation_models, and embeddings.

### What might be worth cherry-picking

1. **`safe_identifier` underscore collapse** (1 line): `safe = re.sub(r"_+", "_", safe)` -- prevents `foo__bar` from CamelCase boundaries
2. **`build_full_models()`** -- Existing code only builds filter and mutation variants; this adds a "full model" (all fields, non-optional). Useful if needed elsewhere, but not currently required.
3. **Test patterns** -- The 1,400 lines of tests are thorough, but they test duplicate code.

### Assessment

**Recommendation: Close.** All core functionality already exists in the codebase. The one-line `safe_identifier` fix can be cherry-picked if needed.

---

## PR #817: "328 graphql utilizing dynamic models"

- **Created:** 2026-01-28 | **Commits:** 5 (includes all 4 from #813) | **Files:** 37
- **Branch:** `328-graphql-utilizing-dynamic-models`
- **Self-described as:** "this one still needs work to get it functioning correctly"

### What it adds (beyond PR #813)

| Component | Lines | Purpose |
|-----------|-------|---------|
| `components/lif/graphql/core.py` | 108 | `Backend` protocol + `HttpBackend` (talks to Query Planner) |
| `components/lif/graphql/schema_factory.py` | 341 | Strawberry schema builder: OpenAPI -> SchemaField -> Pydantic -> Strawberry types |
| `components/lif/graphql/type_registry.py` | 125 | Singleton type registry for caching types (**unused** -- not wired in) |
| `components/lif/graphql/utils.py` | 87 | PascalCase helpers, serialization, selection path extraction |
| `components/lif/openapi_schema/core.py` | 71 | MDR-first schema sourcing with silent file fallback |
| `components/lif/utils/core.py` | 84 | Env var validation utilities |
| `components/lif/utils/strings.py` | 123 | Copy of `string_utils` (**unused** -- nothing imports it) |
| `components/lif/utils/validation.py` | 66 | Truthy/falsy/bool parsing |
| `bases/lif/api_graphql/core.py` | 66 | **Rewritten** app initialization (sync, no auth) |
| Tests | ~1,200 | Tests for new components |

### Architecture comparison

| Aspect | Current (`openapi_to_graphql/`) | PR's approach (`graphql/` + `dynamic_models/` + `schema/`) |
|--------|-------------------------------|--------------------------------------------------|
| Pipeline | OpenAPI dict -> Strawberry types (direct) | OpenAPI -> SchemaField -> Pydantic models -> Strawberry types (3-step) |
| Components | 1 component, ~3 files | 4+ components, ~10 files |
| Mutations | Fully supported | **Commented out** |
| API key auth | Supported via middleware | **Removed entirely** |
| Schema source | `LIFSchemaConfig` + `mdr_client` (fail-loudly) | Silent MDR fallback (**contradicts project policy**) |
| Strawberry bridge | Direct `strawberry.type()` decoration | `strawberry.experimental.pydantic` (marked experimental) |

### Issues found

1. **Mutations disabled** -- commented out in `build_schema()`, only present in dead-code `build_schema_old()`
2. **API key auth removed** -- security regression from current codebase
3. **~200 lines of dead code** -- `build_schema_old()` left in `schema_factory.py`
4. **`type_registry.py` fully implemented but unused** -- not wired into any code path
5. **`utils/strings.py` unused** -- nothing imports it
6. **Stray `print()` statements** in `schema_factory.py` and `openapi_schema/core.py`
7. **Duplicate `get_schema_fields()` functions** -- one in `dynamic_models/core.py` and one in `openapi_schema/core.py` with different env vars
8. **Duplicate utility functions** in `graphql/utils.py` with TODO comments acknowledging the duplication
9. **Silent MDR fallback** contradicts project's "fail loudly" philosophy (CLAUDE.md)
10. **Global mutable state** in `schema_factory.py` (`global RootType, FilterInput, MutationInput`)
11. **`logging.basicConfig()` at module level** in `dynamic_models/core.py` -- resets root logger

### What might be worth adopting

1. **`Backend` protocol pattern** (`graphql/core.py`) -- clean separation of the Query Planner HTTP client behind a protocol. The existing code has this inline. Could be useful for testing.
2. **`extract_selected_fields()` from Strawberry `Info`** -- computes dotted JSON paths from the GraphQL selection set. Not sure if current code does this.
3. **`pydantic_inputs_to_dict()`** -- recursive serializer that handles Pydantic/dataclass/enum/date types. Useful utility if not already covered.
4. **The 3-step type pipeline concept** (OpenAPI -> Pydantic -> Strawberry) -- architecturally cleaner for Pydantic reuse, but adds complexity and uses experimental Strawberry APIs. Not worth adopting now.

### Assessment

**Recommendation: Close.** The code is self-described as non-functional, removes security features (API key auth), disables mutations, contradicts project architecture decisions (schema loading policy), and introduces significant dead code. The existing `openapi_to_graphql/` component, combined with the recent Strawberry version fix (PR #863), handles all of this already.

---

## Summary of action items

| Action | Details |
|--------|---------|
| Close PR #813 | Comment explaining the functionality now exists in `openapi_schema_parser`, `semantic_search_service`, and `schema_state_manager` |
| Close PR #817 | Comment explaining the code is non-functional and the existing `openapi_to_graphql` pipeline (fixed in PR #863) covers the same ground |
| Cherry-pick consideration | `safe_identifier` underscore collapse fix -- evaluate if `lif_schema_config/naming.py` already handles this |
| Delete branches | After closing, delete `328-schema-and-dynamic-models-from-a-and-m` and `328-graphql-utilizing-dynamic-models` |
