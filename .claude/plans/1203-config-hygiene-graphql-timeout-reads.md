# Issue #1203 — Config hygiene: one timeout env var, three meanings

Split the overloaded `LIF_QUERY_TIMEOUT_SECONDS` into per-consumer variables so setting
the Query Planner's ceiling can never silently change GraphQL client timeouts or uvicorn
keep-alive, and fix the two compose services that read a differently-named host variable.

---

## The problem (as found on `main`, HEAD `66fad9c`)

`LIF_QUERY_TIMEOUT_SECONDS` was read by:

| Consumer | Location | Effective value |
|---|---|---|
| GraphQL HTTP client (outbound calls) | `components/lif/openapi_to_graphql/type_factory.py:48,817` | 20 code default |
| uvicorn `--timeout-keep-alive` (ECS / standalone Dockerfile) | `projects/lif_graphql_api/Dockerfile:18-19` | 60 ENV; **300 on ECS** (taskdef overrides) |
| `lif_schema_config.query_timeout_seconds` — dormant field, nothing reads it | `components/lif/lif_schema_config/core.py:192` | 20 code default |
| Query Planner `/query` polling ceiling | **hardcoded `300`** (`query_planner_restapi/core.py:116`); the env-plumbing lives only on the unmerged #571 branch | n/a |

Two compose lines interpolated `LIF_QUERY_TIMEOUT` (no `_SECONDS`) into it, so exporting the
documented `LIF_QUERY_TIMEOUT_SECONDS` left those services on a value nobody intended:
`deployments/advisor-demo-docker/docker-compose.yml:269` (org1) and
`development/advisor-demo-3orgs/docker-compose.yml:156` (org1). org1's override always won
over the graphql environment template's `${LIF_QUERY_TIMEOUT_SECONDS:-300}`, so org1 ran at
**60** while org2/3 ran at 300 (demo) or 20 (3orgs, no var passed → code default). ECS ran
all three meanings at **300**.

## Decisions (confirmed with product/user)

- Rename each consumer to its own variable; `LIF_QUERY_TIMEOUT_SECONDS` is **reserved for the
  Query Planner ceiling** (the name #571 will use), so the QP taskdef line and the QP compose
  lines are untouched.
- Demo compose client-timeout default **normalizes to 300** (the intended value; 60 was never
  deliberate — it came from the wrong host variable) — makes compose consistent with ECS and
  with 3orgs' previously-20 org2/3.
- The dormant `lif_schema_config.query_timeout_seconds` reader is **repointed** to the new
  GraphQL client name (same conceptual knob; keeps `LIF_QUERY_TIMEOUT_SECONDS` to exactly one
  reader).
- ECS taskdef is **wired now** with both new names (behavior-preserving: client 300, keep-alive
  300 — both were 300 on ECS). Requires a coordinated image + taskdef deploy: the code change
  alone would leave ECS passing the old name, falling back to the 20-second client default.

## Changes

- `components/lif/openapi_to_graphql/type_factory.py` — module constant + use site renamed to
  `LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS` (default stays 20).
- `components/lif/lif_schema_config/core.py` — `query_timeout_seconds` env read + `from_environment`
  docstring repointed to `LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS`.
- `projects/lif_graphql_api/Dockerfile` — ENV + `--timeout-keep-alive` use `LIF_GRAPHQL_KEEPALIVE_SECONDS`
  (default stays 60). Compose builds use Dockerfile2 (no keep-alive flag), so compose is unaffected.
- `cloudformation/lif-graphql-taskdef-includes.yml` — `LIF_QUERY_TIMEOUT_SECONDS: 300` replaced by
  `LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS: 300` + `LIF_GRAPHQL_KEEPALIVE_SECONDS: 300`.
  `lif-query-planner-taskdef-includes.yml` left unchanged (`LIF_QUERY_TIMEOUT_SECONDS: 120`, QP-reserved).
- `deployments/advisor-demo-docker/docker-compose.yml` — graphql environment template uses
  `${LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS:-300}`; org1's `LIF_QUERY_TIMEOUT_SECONDS: ${LIF_QUERY_TIMEOUT:-60}`
  override removed (org1 inherits the template). QP services' `LIF_QUERY_TIMEOUT_SECONDS:-120` untouched.
- `development/advisor-demo-3orgs/docker-compose.yml` — graphql template gains
  `LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS: ${LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS:-300}` (fixes org2/3's fallback
  to the 20 code default); org1's `${LIF_QUERY_TIMEOUT:-60}` override removed.
- `cspell.json` — added `dedups` (pre-existing test name tripped cspell on the touched test file).

## Tests

- `test/components/lif/openapi_to_graphql/test_core.py` — `TestGraphQLClientTimeoutEnvReads`:
  fresh-interpreter (CLAUDE.md forbids `importlib.reload`) assertions that type_factory reads
  `LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS`, that the old `LIF_QUERY_TIMEOUT_SECONDS` is inert (→ default 20),
  and that the default is 20. Renaming either string literal back fails the suite.
- `test/components/lif/lif_schema_config/test_core.py` — `from_environment` reads
  `LIF_GRAPHQL_CLIENT_TIMEOUT_SECONDS` and ignores `LIF_QUERY_TIMEOUT_SECONDS`.

## Verification

- `uv run pytest test/components/lif/openapi_to_graphql/ test/components/lif/lif_schema_config/` — 46 passed.
- Additions unaffected by the pre-existing, unrelated `api_graphql::test_fetch_dynamic_graphql_schema`
  failure (fails identically on clean `main`).
- `uv run ruff check/format`, `ty check`, YAML-parse of both compose files + both taskdefs — clean.
- `uv run pre-commit run --files <all 9 changed files>` — all hooks pass.

## Out of scope

Making the Query Planner polling ceiling configurable (#571 — env plumbing is unmerged); retiring
`LIF_QUERY_TIMEOUT_SECONDS` entirely (it stays, reserved for QP); `#1179`'s unguarded
`int(os.getenv(...))` at module scope.