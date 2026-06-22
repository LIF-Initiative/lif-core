# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LIF Core (Learner Information Framework) is a modular monorepo for aggregating learner information from multiple systems (SIS, LMS, HR) into standardized data records. Uses **Polylith architecture** for clean separation between reusable business logic and deployment contexts.

## Companion docs

`CLAUDE.md` is the dense agent-oriented map. For deeper / more human-readable coverage of the same material, see:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — repo-root landing page with polylith primer + service-map Mermaid diagram.
- [`docs/INDEX.md`](docs/INDEX.md) — curated one-line-per-doc index of everything under `docs/`.
- [`docs/overview/services-overview.md`](docs/overview/services-overview.md) — per-service responsibilities, endpoints, and inter-service flows.
- [`docs/design/cross-cutting/self-serve-tenant-auth.md`](docs/design/cross-cutting/self-serve-tenant-auth.md) — Cognito sign-up → schema-per-tenant → workspace selection → invite tokens (#882/#883/#884).
- [`docs/specs/data-model-rules.md`](docs/specs/data-model-rules.md) — PascalCase entities vs camelCase scalars and the files that must follow the convention.
- [`docs/operations/guides/adding-a-new-microservice.md`](docs/operations/guides/adding-a-new-microservice.md) — runbook for standing up a new HTTP service (Polylith brick layout, pyproject hygiene, Dockerfile2, AuthMiddleware, compose wiring).

Detail extracted from this file lives in:

- [`docs/operations/guides/testing.md`](docs/operations/guides/testing.md) — unit/integration test principles, sample data, test users, service-layer order.
- [`docs/design/cross-cutting/schema-loading.md`](docs/design/cross-cutting/schema-loading.md) — schema loading pattern, `SchemaStateManager`, PascalCase/camelCase convention, Strawberry GraphQL details.
- [`docs/design/components/semantic-search.md`](docs/design/components/semantic-search.md) — semantic search MCP server architecture, endpoints, tools.
- [`docs/operations/guides/graphql-api-keys.md`](docs/operations/guides/graphql-api-keys.md) — GraphQL org1 API key auth and key management.
- [`docs/operations/guides/deployment.md`](docs/operations/guides/deployment.md) — deployment scripts, env config, MDR migrations, ECS debugging, Docker build gotchas.

Each base and component also has a brick-level `README.md` describing purpose, public surface, and consumers.

## Commands

### Setup
```bash
uv sync                                    # Create venv and install dependencies
uv run pre-commit install                  # Install pre-commit hooks
uv run pre-commit install --hook-type commit-msg  # Install commit-msg hooks
```

### Development
```bash
uv run ruff check                          # Lint code
uv run ruff format                         # Format code
uv run ty check                            # Type check
uv run pytest test/                        # Run all tests
uv run pytest test/components/lif/foo/     # Run tests for specific component
uv run pre-commit run --all-files          # Run all checks (lint, format, type, test)
```

### Building Services
```bash
cd projects/lif_advisor_api && bash build.sh        # Build wheel package
cd projects/lif_advisor_api && bash build-docker.sh # Build Docker image
```

## Architecture

### Polylith Structure
```
components/     # Reusable business logic (no deployment code)
bases/          # Deployment contexts (REST APIs, GraphQL, MCP servers)
projects/       # Executable applications combining bases + components
```

- **Components** (`components/lif/`): Self-contained modules with `core.py` entrypoint. Must be purely logical, testable in isolation, no I/O or deployment code.
- **Bases** (`bases/lif/`): Deployment wrappers (FastAPI apps, etc.) that compose components. Keep business logic out—just orchestration glue.
- **Projects** (`projects/`): Docker-ready executables with `pyproject.toml`, `build.sh`, `Dockerfile`.

### Key Services
- **GraphQL API** (`api_graphql`) - Query interface for learner data
- **Advisor API** (`advisor_restapi`) - AI-powered conversational interface (LangChain-based)
- **Translator** (`translator_restapi`) - Transform source data to LIF format
- **MDR** (`mdr_restapi`) - Metadata/schema management
- **Query Planner** (`query_planner_restapi`) - Query routing and optimization
- **Query Cache** (`query_cache_restapi`) - Caching layer
- **Semantic Search MCP Server** (`semantic_search_mcp_server`) - Claude MCP integration

### Key Components (Shared Libraries)
- **`graphql_client`** - Authenticated HTTP client for GraphQL API calls (sends `X-API-Key` header)
- **`mdr_client`** - Authenticated HTTP client for MDR API calls
- **`schema_state_manager`** - Shared schema loading/state for services needing OpenAPI schema data
- **`lif_schema_config`** - Centralized schema configuration (`LIFSchemaConfig`)

### Other Directories
- `frontends/` - React/TypeScript UI apps
- `orchestrators/dagster/` - Data orchestration job definitions (development/local use)
- `deployments/` - Environment-specific Docker Compose configs
- `cloudformation/` - AWS IaC templates
- `test/` - Tests mirror source structure (`test/components/`, `test/bases/`)
- `docs/` - Technical documentation (MkDocs)

### Dagster Projects (IMPORTANT)
Docker builds for Dagster use projects in `projects/dagster_*/`, NOT `orchestrators/dagster/lif-orchestrator/`:
- `projects/dagster_docker_compose/` - Local Docker Compose deployment
- `projects/dagster_plus_hybrid/` - Dagster Cloud hybrid deployment
- `projects/dagster_oss_ecs/` - AWS ECS deployment

When adding new component dependencies (polylith bricks) needed by Dagster jobs, you must update the `[tool.polylith.bricks]` section in ALL THREE of these `pyproject.toml` files, not just the orchestrator.

## Code Conventions

### File layout (Python)

In modules that combine Pydantic models, helper functions, and FastAPI endpoint handlers (typical shape of `bases/lif/*_restapi/core.py` and router modules), group each category contiguously:

1. **Pydantic request/response models** at the top
2. **Helper functions** in the middle
3. **Endpoint handlers** at the bottom

Don't interleave. Small modules with one model and one endpoint can skip this; the convention scales with file size. Also see [CONTRIBUTING.md → File layout](CONTRIBUTING.md#file-layout-python).

## Commit Convention

Commits must follow this pattern:
```
Issue #XXX: Brief description
```

Multiple issues: `Issue #123, Issue #456: Description`

Types encouraged: `feat:`, `fix:`, `docs:`, `refactor:`

## Testing

- Unit tests in `test/` mirror source structure; pytest with `asyncio_mode = auto`. Write tests that earn their keep (non-trivial logic, boundaries, bug regressions) — skip trivial wrappers and framework behavior.
- **Avoid `importlib.reload()` in tests** — it breaks `isinstance()`/`pytest.raises()` matching. Use `mock.patch.object(module, "VAR_NAME", value)` instead.
- Integration tests in `integration_tests/` verify data consistency across the full stack, dynamically loading sample data from `projects/mongodb/sample_data/{org-key}/`.

Full reference (test principles, sample data orgs, the 6 test users, service-layer order): [`docs/operations/guides/testing.md`](docs/operations/guides/testing.md).

## Pre-commit Hooks

All enforced automatically on commit:
1. `uv-lock` - Lock file validation
2. `ruff-check --fix` - Linting with auto-fix
3. `ruff-format` - Formatting
4. `cspell` - Spell checking
5. `ty check --error-on-warning` - Type checking
6. `pytest test` - Tests

## LIF Schema & Data Model

- **Source of truth**: `reference_data/schemas/lif-schema.json` → captured dynamically by MDR → seed data, components, and GraphQL queries all honor the MDR schema.
- **Loaded from MDR at startup** via `LIFSchemaConfig.from_environment()` and the `SchemaStateManager` component. **No silent fallback to bundled file** — if MDR is configured but unavailable, the service fails loudly. `USE_OPENAPI_DATA_MODEL_FROM_FILE=true` forces the bundled file (dev only).
- **Capitalization convention**: entity/object/array properties are **PascalCase** (`Name`, `Identifier`, `EmploymentPreferences`); scalar attributes are **camelCase** (`firstName`, `identifierType`). Applies to seed data, `.graphql` queries, `information_sources_config*.yml` fragment paths, and test fixtures.

Full reference (schema hierarchy, `SchemaStateManager` usage, the convention's affected files, and Strawberry GraphQL implementation details): [`docs/design/cross-cutting/schema-loading.md`](docs/design/cross-cutting/schema-loading.md). Normative rules: [`docs/specs/data-model-rules.md`](docs/specs/data-model-rules.md).

## Semantic Search MCP Server

`bases/lif/semantic_search_mcp_server/` exposes MCP tools (`lif_query`, `lif_mutation`) for AI-powered learner data queries — FastMCP + Sentence-Transformers embeddings, loading schema from MDR at startup and querying org1's GraphQL API (Docker port 8003). See [`docs/design/components/semantic-search.md`](docs/design/components/semantic-search.md).

## GraphQL API Key Authentication

GraphQL org1 accepts API keys managed in AWS SSM. The server validates incoming `X-API-Key` headers against `GRAPHQL_AUTH__API_KEYS` (disabled when empty); clients send `LIF_GRAPHQL_API_KEY` via the `graphql_client` component. Key management (`scripts/setup-graphql-api-keys.sh`, service vs. workshop modes) and redeploy steps: [`docs/operations/guides/graphql-api-keys.md`](docs/operations/guides/graphql-api-keys.md).

## Deployment & Operations

- Environments: `dev` (uses `:latest` image tags, single-org) and `demo` (pinned version tags, multi-org), manually promoted from dev. Config in `{env}.aws` files and `cloudformation/{env}-*.params`.
- Deploy with `aws-deploy.sh`; promote images with `scripts/release-demo.sh`. **Deploy sequentially** — parallel runs cause SSO login conflicts.
- **MDR migrations (V1.2+) must be idempotent** (`CREATE OR REPLACE`, `IF NOT EXISTS`) — local docker-compose replays every `V1.*.sql` through `psql` without Flyway history tracking.
- **PEP 440 `~=` gotcha**: `~=0.275` means `< 1.0`, not `< 0.276`; use `~=0.275.0` to pin a minor range. (Caused a prod crash via Docker wheel resolution.)

Full reference (script table, env differences, Docker build resolution, ECS/CloudWatch debugging, MDR API querying): [`docs/operations/guides/deployment.md`](docs/operations/guides/deployment.md). Demo promotion walkthrough: [`docs/operations/guides/demo-environment-update.md`](docs/operations/guides/demo-environment-update.md).

## Key Technologies

- Python 3.13, FastAPI, Strawberry GraphQL, SQLAlchemy/SQLModel
- Dagster (orchestration), LangChain/LangGraph (AI agents)
- FastMCP (Model Context Protocol), Sentence-Transformers (semantic search)
- MongoDB, PostgreSQL/MySQL support
