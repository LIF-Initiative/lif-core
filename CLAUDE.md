# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LIF Core (Learner Information Framework) is a modular monorepo for aggregating learner information from multiple systems (SIS, LMS, HR) into standardized data records. Uses **Polylith architecture** for clean separation between reusable business logic and deployment contexts.

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

## Commit Convention

Commits must follow this pattern:
```
Issue #XXX: Brief description
```

Multiple issues: `Issue #123, Issue #456: Description`

Types encouraged: `feat:`, `fix:`, `docs:`, `refactor:`

## Testing

### Unit Tests
- Tests are in `test/` mirroring source structure
- Uses pytest with `asyncio_mode = auto`
- Run specific module tests: `uv run pytest test/components/lif/<module>/`
- **Avoid `importlib.reload()` in tests** — reloading a module creates new class objects, breaking `isinstance()` checks and `pytest.raises()` matching. Use `mock.patch.object(module, "VAR_NAME", value)` to override module-level variables instead.

### Integration Tests

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

## Pre-commit Hooks

All enforced automatically on commit:
1. `uv-lock` - Lock file validation
2. `ruff-check --fix` - Linting with auto-fix
3. `ruff-format` - Formatting
4. `cspell` - Spell checking
5. `ty check --error-on-warning` - Type checking
6. `pytest test` - Tests

## LIF Schema & Data Model

### Schema Hierarchy
1. **`schemas/lif-schema.json`** - Source of truth for LIF data model rules and policies
2. **MDR (Metadata Registry)** - Captures schema dynamically, allows extension by deployers
3. **Seed data** - Must validate against the schema from MDR
4. **Components** - Must honor the schema, load from MDR with short cache if needed
5. **GraphQL queries** - Should align with schema as best as practical

### Schema Loading Pattern (IMPORTANT)

Services load OpenAPI schema from MDR at startup. Key design decisions:

**No silent fallback to file:**
- If MDR is configured but unavailable, the service **fails with a clear error** (does not silently fall back to bundled file)
- This prevents using stale/outdated schema data in production
- Use `USE_OPENAPI_DATA_MODEL_FROM_FILE=true` to explicitly use bundled file (development only)

**Configuration via `LIFSchemaConfig`:**
- All schema-related config should use `LIFSchemaConfig.from_environment()` (not direct `os.getenv()`)
- Provides centralized validation and consistent defaults
- Key env vars: `OPENAPI_DATA_MODEL_ID`, `LIF_MDR_API_URL`, `USE_OPENAPI_DATA_MODEL_FROM_FILE`

**SchemaStateManager component** (`components/lif/schema_state_manager/`):
- Shared component for services that need schema data (semantic search, GraphQL)
- Handles sync and async initialization
- Thread-safe state access via lock
- Tracks schema source ("mdr" or "file")
- Supports schema refresh without restart

```python
from lif.schema_state_manager import SchemaStateManager
from lif.lif_schema_config import LIFSchemaConfig

config = LIFSchemaConfig.from_environment()
manager = SchemaStateManager(config)
manager.initialize_sync()  # or await manager.initialize()

state = manager.state  # Access schema leaves, filter models, embeddings
```

### Capitalization Convention (IMPORTANT)

The LIF schema uses a specific naming convention based on data type:

| Type | Case | Examples |
|------|------|----------|
| **Entity/Object/Array properties** | PascalCase | `Name`, `Contact`, `Identifier`, `EmploymentLearningExperience`, `CredentialAward`, `Proficiency` |
| **Scalar attributes** | camelCase | `firstName`, `lastName`, `identifier`, `identifierType`, `informationSourceId`, `startDate` |

**Example structure:**
```json
{
  "person": [{
    "Name": [{                           // PascalCase - array of objects
      "firstName": "John",               // camelCase - scalar attribute
      "lastName": "Doe",
      "informationSourceId": "Org1"
    }],
    "Identifier": [{                     // PascalCase - array of objects
      "identifier": "12345",             // camelCase - scalar attribute
      "identifierType": "SCHOOL_ASSIGNED_NUMBER"
    }],
    "EmploymentPreferences": [{          // PascalCase - array of objects
      "organizationTypes": ["Public"]    // camelCase - scalar attribute
    }]
  }]
}
```

### Files That Must Follow This Convention
- **Seed data**: `projects/mongodb/sample_data/**/*.json`
- **GraphQL queries**: `components/lif/data_source_adapters/**/*.graphql`
- **Config files**: `deployments/**/information_sources_config*.yml` (fragment paths like `person.Name`)
- **Test fixtures**: Any test data in `test/`

### Key Implementation Details

1. **Strawberry GraphQL types** (`type_factory.py`):
   - Uses `strawberry.field(name=field_name)` to preserve original schema case
   - `resolve_actual_type()` preserves `List` wrappers for proper type resolution
   - `dict_to_dataclass()` handles nested type conversion

2. **Fragment paths** use format `person.EntityName` (e.g., `person.EmploymentPreferences`)

3. **Translator service** returns data with PascalCase root (`Person` not `person`)
   - The `adjust_lif_fragments_for_initial_orchestrator_simplification()` function uses case-insensitive key lookup to handle this

4. **Filter inputs** in GraphQL also use PascalCase for entity names:
   ```graphql
   person(filter: { Identifier: { identifier: "12345", identifierType: "..." } })
   ```

## Semantic Search MCP Server

The semantic search service (`bases/lif/semantic_search_mcp_server/`) provides MCP tools for AI-powered learner data queries.

**Architecture:**
- Uses FastMCP for Model Context Protocol
- Loads schema from MDR at startup (sync initialization required for tool registration)
- Connected to org1's GraphQL API for data queries
- Embeddings computed via Sentence-Transformers

**HTTP Endpoints:**
- `GET /health` - Readiness check
- `GET /schema/status` - Schema metadata (source, leaf count, roots, filter models)
- `POST /schema/refresh` - Reload schema from MDR (state only, not tool definitions)

**MCP Tools:**
- `lif_query` - Semantic search over LIF data fields
- `lif_mutation` - Update LIF data fields (if mutation model available)

**Docker port:** 8003 (exposed for integration testing)

**GraphQL authentication:** Uses `graphql_client` component for all GraphQL HTTP calls, which automatically sends `X-API-Key` from the `LIF_GRAPHQL_API_KEY` env var when set.

## GraphQL API Key Authentication

GraphQL org1 supports API key authentication. Keys are managed in AWS SSM Parameter Store.

**How it works:**
- Server-side: `/{env}/graphql-org1/ApiKeys` stores comma-separated `key:client-name` pairs (e.g., `abc123:semantic-search,def456:workshop-01`)
- Client-side: Each client has its own SSM param with the bare key (e.g., `/{env}/semantic-search/GraphqlApiKey`)
- The `graphql_client` component reads `LIF_GRAPHQL_API_KEY` env var and sends it as `X-API-Key` header
- GraphQL server validates incoming keys against its `GRAPHQL_AUTH__API_KEYS` env var
- When `GRAPHQL_AUTH__API_KEYS` is empty/unset, authentication is disabled (local dev default)

**Key env vars:**
| Variable | Service | Purpose |
|----------|---------|---------|
| `GRAPHQL_AUTH__API_KEYS` | GraphQL org1 | Server-side: comma-separated `key:label` pairs to accept |
| `LIF_GRAPHQL_API_KEY` | Semantic search | Client-side: bare API key to send with requests |

**Managing keys:**
```bash
# Preview what will happen
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo

# Create/update service key (semantic-search)
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --apply

# Generate workshop participant keys
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --workshop 10 --apply

# Remove all workshop keys (preserves service keys)
AWS_PROFILE=lif ./scripts/setup-graphql-api-keys.sh demo --workshop 0 --apply
```

After key changes, redeploy affected services:
```bash
./aws-deploy.sh -s demo --only-stack demo-lif-semantic-search
./aws-deploy.sh -s demo --only-stack demo-lif-graphql-org1
```

## Deployment & Operations

### Environment Configuration
- `{env}.aws` files (repo root) — define `AWS_REGION`, `SAM_CONFIG_ENV`, `STACKS` map, and `STACK_ORDER` for each environment
- `cloudformation/{env}-*.params` — CloudFormation parameter files per stack, including `ImageUrl` for ECS services
- Environments: `dev`, `demo` (demo is manually promoted from dev)

### Deployment Scripts

| Script | Purpose |
|--------|---------|
| `aws-deploy.sh` | Deploy CloudFormation stacks (`-s demo`, `--only-stack`, `--update-ecs`, `--update-sam`) |
| `release-demo.sh` | Update demo param files with latest ECR image tags from dev |
| `release-demo-frontend.sh` | Build and deploy MDR frontend to S3/CloudFront from a git ref |
| `verify-demo-images.sh` | Compare param file image tags against running ECS tasks |
| `scripts/setup-mdr-api-keys.sh` | Generate and store MDR service API keys in SSM Parameter Store |
| `scripts/setup-graphql-api-keys.sh` | Generate and store GraphQL org1 API keys in SSM (service + workshop modes) |
| `scripts/reset-mdr-database.sh` | Reset MDR database (flyway clean + migrate) when V1.1 SQL is replaced |
| `sam/deploy-sam.sh` | Build Flyway Docker image, push to ECR, run SAM deploy for database stacks |

### Environment Differences
- **Dev** uses `:latest` ECR image tags in param files; **demo** uses pinned version tags (e.g., `:1.2.3`)
- `release-demo.sh` copies the current dev image tags to demo param files for promotion
- Dev has a single-org setup (`dev-single-org`); demo has multi-org (`advisor-demo-org1/2/3`)

### Key Operational Notes
- **Demo update guide**: See `docs/guides/demo_environment_update.md` for the full end-to-end process
- **SAM databases**: See `sam/README.md` for database deployment architecture and Flyway migration details
- **Apple Silicon**: Docker images for Lambda must use `--platform linux/amd64` (already handled in scripts)
- **SSM parameters**: ECS tasks fail to start if referenced SSM parameters are missing, even optional ones like `ApiKeys`
- **Deploy sequentially**: Running multiple `aws-deploy.sh` commands in parallel causes SSO login conflicts
- **MDR frontend**: Deployed to S3 + CloudFront (not ECS); use `release-demo-frontend.sh` for demo
- **Bash `grep -v` with `pipefail`**: In scripts using `set -o pipefail`, `grep -v` returns exit code 1 when all lines are filtered out (no matches). Wrap in `(grep -v ... || true)` to prevent script failure.

## Key Technologies

- Python 3.13, FastAPI, Strawberry GraphQL, SQLAlchemy/SQLModel
- Dagster (orchestration), LangChain/LangGraph (AI agents)
- FastMCP (Model Context Protocol), Sentence-Transformers (semantic search)
- MongoDB, PostgreSQL/MySQL support
