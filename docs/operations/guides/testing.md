# Testing

How tests are organized and what's worth testing in LIF Core. Quick commands live in [`CLAUDE.md → Commands`](../../../CLAUDE.md#commands); this is the full reference.

## Unit Test Principles

Write tests that earn their keep. Every test should justify its existence by verifying something non-obvious.

**What to test:**
- **Non-trivial transformations** — regex, recursion, type dispatch, multi-step logic where inputs interact in non-obvious ways
- **Boundary conditions** — empty inputs, None values, edge cases where behavior changes (e.g., leading digits in identifiers)
- **Regression tests for bugs** — every bug fix should include a test that would have caught it. The test should fail without the fix.
- **Integration-style unit tests** — testing a function end-to-end with real inputs is more valuable than mocking every internal call (e.g., test `generate_graphql_schema()` with a real schema, not with mocked sub-functions)

**What not to test:**
- **Trivial wrappers** — if a function is a one-liner delegating to another tested function (e.g., `".".join([f(x) for x in path.split(".")])`)
- **Framework behavior** — don't test that Pydantic validates types or that `re.sub` works; test *your* logic
- **Obvious guard clauses** — `if not s: return s` doesn't need its own test case unless the empty-input behavior is part of a documented contract
- **Coverage for coverage's sake** — a placeholder test like `assert module is not None` has no value; either write a real test or leave the file empty

## Unit Test Mechanics
- Tests are in `test/` mirroring source structure
- Uses pytest with `asyncio_mode = auto`
- Run specific module tests: `uv run pytest test/components/lif/<module>/`
- **Avoid `importlib.reload()` in tests** — reloading a module creates new class objects, breaking `isinstance()` checks and `pytest.raises()` matching. Use `mock.patch.object(module, "VAR_NAME", value)` to override module-level variables instead.

## Integration Tests

Integration tests are in `integration_tests/` and verify data consistency across the full service stack.

```bash
uv run pytest integration_tests/                    # Run all integration tests
uv run pytest integration_tests/ --org org1         # Run for specific org
uv run pytest integration_tests/ --skip-unavailable # Skip tests for unavailable services
```

**Key design principles:**
- Tests **dynamically load sample data** from JSON files at runtime (no hardcoded constants)
- The `SampleDataLoader` class reads from `projects/mongodb/sample_data/{org-key}/`
- Tests compare API responses against dynamically loaded expected values
- If sample data changes, tests automatically adapt

**Sample data organization:**
```
projects/mongodb/sample_data/
├── advisor-demo-org1/    # Matt, Renee, Sarah, Tracy (4 users)
├── advisor-demo-org2/    # Alan, Jenna, Sarah, Tracy (4 users)
├── advisor-demo-org3/    # Alan, Jenna, Matt, Renee (4 users)
└── dev-single-org/       # All 6 users combined
```

**Test users (6 total unique):**
| User | Native Org | Notes |
|------|-----------|-------|
| Matt | org1 | Core user |
| Renee | org1 | Core user |
| Sarah | org1 | Core user |
| Tracy | org1 | Core user |
| Alan | org2 | Async-ingested into org1 via orchestration |
| Jenna | org2 | Async-ingested into org1 via orchestration |

**Testing async-ingested users:**
- Core users (org1 native) must always be present - tests fail if missing
- Async users (from org2/org3) warn/skip if not yet ingested
- To verify actual ingestion, tests query GraphQL directly (not just sample files)
- GraphQL queries require specific identifiers - empty filter `{}` returns empty results

**Service layer testing order:**
1. `test_01_mongodb.py` - Direct MongoDB verification
2. `test_02_query_cache.py` - Query cache layer
3. `test_03_query_planner.py` - Query planner routing
4. `test_04_graphql.py` - GraphQL API layer
5. `test_05_cross_org.py` - Cross-organization data isolation
6. `test_06_semantic_search.py` - Semantic search MCP server
