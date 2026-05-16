# Adding a New Microservice

> **Related:** [`creating-a-data-source-adapter.md`](creating-a-data-source-adapter.md) covers adapters specifically. This guide covers standing up an entirely new HTTP service (REST API, MCP server, etc.).

This guide walks through what you actually have to do to add a microservice the rest of LIF can deploy, deploy alongside, and call. It assumes you've already decided *what* the service does — this is mechanical.

If you've done this once, the checklist at the bottom is probably all you need.

## Mental model: Polylith bricks

LIF uses [Polylith](https://polylith.gitbook.io/). The three concepts:

- **Components** (`components/lif/`) — Reusable business logic. No I/O, no FastAPI, no deployment code. A component's only "interface" is its public Python imports.
- **Bases** (`bases/lif/`) — Deployment wrappers. FastAPI app definitions, route handlers, middleware composition. Bases pull from components.
- **Projects** (`projects/`) — Executable applications. A project's `pyproject.toml` lists which components and which base it composes into a wheel, and provides Docker scaffolding.

For a new microservice, you'll almost always touch all three: a new base, possibly a new component (if there's reusable logic worth sharing), and a new project that ties them together.

## Step 1: Create the base

```
bases/lif/my_new_service/
├── __init__.py            # exposes core for the project to import
├── core.py                # FastAPI app, middleware, route registration
└── my_endpoints.py        # one or more route modules
```

### `__init__.py`

```python
from lif.my_new_service import core

__all__ = ["core"]
```

### `core.py` — the FastAPI app

Minimum scaffold:

```python
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lif.datatypes.core import HealthCheckResponse
from lif.logging import get_logger
from lif.mdr_auth.core import AuthMiddleware
from lif.mdr_utils.config import get_settings
from lif.my_new_service import my_endpoints

logger = get_logger(__name__)
settings = get_settings()
app = FastAPI(title="LIF My New Service", description="...", version="1.0.0")

app.add_middleware(AuthMiddleware)
# ...CORS setup omitted; copy from an existing service...

@app.get("/health-check", response_model=HealthCheckResponse)
async def health_check():
    return HealthCheckResponse(status=HTTPStatus.OK, message="API is healthy")

app.include_router(my_endpoints.router, prefix="")
```

### Common pitfalls in `core.py`

- **Logger consistency.** Use `from lif.logging import get_logger` (matches `advisor_restapi`, `api_graphql`, `semantic_search_mcp_server`, etc.). Don't mix in `from lif.mdr_utils.logger_config import get_logger` — that's the MDR-internal logger with a different output format. Pick one and use it consistently across all files in your base.
- **AuthMiddleware vs raw FastAPI auth.** If the service is internal-only, use `AuthMiddleware` from `lif.mdr_auth.core` — it handles API-key, Cognito JWT, and legacy HS256 callers consistently with the rest of LIF. Don't reinvent.

## Step 2: Create the project

```
projects/lif_my_new_service/
├── .dockerignore
├── .gitignore
├── Dockerfile             # legacy build (some services still ship this)
├── Dockerfile2            # current canonical Dockerfile
├── README.md
├── build-docker.sh
├── build.sh
└── pyproject.toml
```

Copy `.dockerignore`, `.gitignore`, `build.sh`, and `build-docker.sh` from a similar project verbatim — they don't vary.

### `pyproject.toml` — **do not copy dependencies wholesale**

This is the single most common source of bloat. Look at what your code actually imports, and declare *that*. A REST API typically needs only:

```toml
dependencies = [
    "fastapi~=0.115",
    "uvicorn~=0.34",
]
```

Add `httpx` or `requests` if you'll call other services. Add `pyjwt` if you need direct JWT operations. Add SQL drivers only if you actually open a database connection.

**Don't add `langchain`, `langgraph`, `langmem`, `mcp`, etc. unless your service genuinely uses them.** Copying the advisor API's dep block pulls in hundreds of MB of transitive dependencies (torch, transformers, etc.) and bloats your Docker image accordingly.

**PEP 440 gotcha:** `~=0.275` means `>= 0.275, < 1.0`, NOT `>= 0.275, < 0.276`. To pin to a minor range, write `~=0.275.0`. This has caused a production crash in the past (strawberry-graphql); CLAUDE.md tracks the war story.

### `pyproject.toml` — bricks

```toml
[tool.polylith.bricks]
"../../bases/lif/my_new_service" = "lif/my_new_service"
"../../components/lif/datatypes" = "lif/datatypes"
"../../components/lif/logging" = "lif/logging"
"../../components/lif/mdr_auth" = "lif/mdr_auth"
"../../components/lif/mdr_utils" = "lif/mdr_utils"
"../../components/lif/tenant_routing" = "lif/tenant_routing"
```

**Only list bricks your code actually imports.** Dead entries here are confusing and review-flag bait. After you have the code written, run:

```bash
grep -rhn '^from lif\.' bases/lif/my_new_service/ | sort -u
```

— every `lif.X` import in your base needs a matching brick line; every brick line should match at least one import. Mismatches indicate either a missing dep or dead config.

### `Dockerfile2`

Copy verbatim from an existing project (e.g., `projects/lif_advisor_api/Dockerfile2`), changing only `PROJECT_NAME` and the final `--port` and `uvicorn` target.

The runtime stage installs the wheel with `uv pip install --system`, which resolves dependencies from PyPI based on the wheel's metadata constraints — **not** from `uv.lock`. This means **a dependency must be declared in *this project's* `pyproject.toml`, not just at the monorepo root, to be available in the Docker image.** Putting `boto3` in the root `pyproject.toml` only is a known landmine.

### `README.md`

Three sections: what the service does, how to build it, example curl calls.

## Step 3: Wire into auth (if internal-only)

If your service is called by other services using a service API key:

1. Add a config entry in `components/lif/mdr_utils/config.py`:
   ```python
   mdr__auth__service_api_key__my_new_service: str = "changeme7"
   ```
2. Add the key to the `API_KEYS` dict in `components/lif/mdr_auth/core.py`:
   ```python
   API_KEYS = {
       ...
       settings.mdr__auth__service_api_key__my_new_service: "my-new-service",
   }
   ```

**Semantic clarification on the key naming:** `mdr__auth__service_api_key__my_new_service` is added to a *server-side* accept-list. Every service running `AuthMiddleware` will accept this key. Naming it `..._my_new_service` is conventional but technically "this is the key callers use *when they identify as* my-new-service." It's not "the key my-new-service presents to others" — that's a separate-but-related concern; see the comment on PR #920 for the conversation.

## Step 4: Add to docker-compose

In `deployments/advisor-demo-docker/docker-compose.yml`, follow the existing service blocks. Minimum entries:

```yaml
lif-my-new-service:
  build:
    context: ../../
    dockerfile: projects/lif_my_new_service/Dockerfile2
  container_name: lif-my-new-service
  environment:
    CORS_ALLOW_ORIGINS: ${CORS_ALLOW_ORIGINS:-http://localhost:3000,...}
    CORS_ALLOW_CREDENTIALS: ${CORS_ALLOW_CREDENTIALS:-true}
    MDR__AUTH__SERVICE_API_KEY__MY_NEW_SERVICE: ${MDR__AUTH__SERVICE_API_KEY__MY_NEW_SERVICE:-changeme7}
    MDR__AUTH__METHODS_TO_REQUIRE_AUTH: ${MDR__AUTH__METHODS_TO_REQUIRE_AUTH:-GET,POST,PUT,DELETE}
    MDR__AUTH__PUBLIC_ALLOWLIST_EXACT: ${MDR__AUTH__PUBLIC_ALLOWLIST_EXACT:-/health-check}
    MDR__AUTH__PUBLIC_ALLOWLIST_STARTS_WITH: ${MDR__AUTH__PUBLIC_ALLOWLIST_STARTS_WITH:-/docs,/openapi.json}
  ports:
    - "80NN:80NN"  # pick an unused port; see existing services for the assigned range
  networks:
    - lif-net-org1  # add others if cross-org
  healthcheck:
    test: ["CMD", "python", "-c", "import sys,urllib.request; sys.exit(0) if urllib.request.urlopen('http://localhost:80NN/health-check').status==200 else sys.exit(1)"]
    interval: 15s
    timeout: 10s
    retries: 3
    start_period: 10s
  depends_on:
    # whatever your service actually needs at startup
```

**Don't** list `MDR__AUTH__SERVICE_API_KEY__*` for keys your service doesn't actually call with — it confuses readers about who calls what.

## Step 5: Add a GitHub Actions deploy workflow

Copy an existing workflow (e.g., `.github/workflows/lif_advisor_api.yml`). The triggers are:

```yaml
on:
  workflow_dispatch:
  push:
    branches: [ "main" ]
    paths:
      - .github/workflows/lif_my_new_service.yml
      - projects/lif_my_new_service/**
      - bases/lif/my_new_service/**
      # plus any components your service uses
```

**Feature branches don't auto-deploy.** Dev ECR `:latest` only rebuilds on push-to-main or manual `workflow_dispatch`. If you need your feature-branch code in dev to test integrations, you'll have to dispatch the workflow by hand.

## Step 6: Add CloudFormation

Add a CloudFormation template under `cloudformation/` for your service's ECS task definition, ALB rules, and SSM parameters. Mirror an existing one. Register the stack in `dev.aws` and `demo.aws` under `STACKS` and `STACK_ORDER`.

If this is your first stack, ask for a pairing session — there are several environment-specific decisions (ALB listener priorities, SSM parameter paths, etc.) that are easier to get right with an architect.

## Step 7: Tests

Mirror the source tree under `test/`. At minimum:

- One test that the health-check endpoint returns 200 without auth.
- One test that an authenticated endpoint returns 401 without a key.
- One test that an authenticated endpoint returns its expected payload with a valid key.

Use `httpx.AsyncClient(transport=ASGITransport(app=app), ...)` to exercise the app in-process — no need for a real running container. See `test/bases/lif/mdr_restapi/test_tenant_endpoints.py` for the pattern, including how to override `get_session` and stub auth principals.

## Checklist before opening the PR

```
□ Base under bases/lif/<service>/ with core.py + endpoints
□ Project under projects/lif_<service>/ with pyproject.toml, Dockerfile2, build.sh, build-docker.sh, README.md
□ pyproject.toml dependencies trimmed to what's actually imported
□ pyproject.toml [tool.polylith.bricks] matches actual imports (no dead entries)
□ Logger imports consistent (lif.logging throughout)
□ /health-check endpoint in the public allowlist
□ Service API key added to config + API_KEYS dict (if internal-only)
□ docker-compose service entry with env vars and healthcheck
□ GitHub Actions workflow file
□ CloudFormation template + registration in {env}.aws files
□ Tests: health-check, auth-required, happy path
□ uv run ruff check + uv run pytest + uv run ty check all clean (or matched against main's baseline)
```
