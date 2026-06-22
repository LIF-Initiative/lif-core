---
name: new-microservice
description: Stand up a new LIF HTTP service end-to-end — Polylith base + project + auth wiring + docker-compose + GitHub Actions + CloudFormation + tests — as an executable checklist with the known pyproject/brick/Docker pitfalls baked in.
argument-hint: <service-name>
allowed-tools: Read, Edit, Write, Bash, Glob, Grep, Agent
---

Add a new microservice the rest of LIF can build, deploy alongside, and call. This is the executable form of [`docs/operations/guides/adding-a-new-microservice.md`](../../../docs/operations/guides/adding-a-new-microservice.md) — **read that guide first**; it is the source of truth and this skill tracks it. This skill adds the workflow gates, the pitfalls, and the verification steps.

## Arguments

- `<service-name>` — snake_case service name (e.g. `roster_sync`, `credential_verify`). Becomes the base `bases/lif/<service-name>/`, project `projects/lif_<service-name>/`, and stack `{env}-lif-<service-with-dashes>`.

## Pre-flight

1. **Read the guide** ([`adding-a-new-microservice.md`](../../../docs/operations/guides/adding-a-new-microservice.md)) and the Polylith / Docker sections of [`CLAUDE.md`](../../../CLAUDE.md).
2. **Confirm what the service does** and whether it's internal-only (uses `AuthMiddleware` + a service API key) or has a public surface. Pick an unused docker-compose port (check existing services for the assigned range).
3. **Find the nearest existing service to copy from.** `advisor_restapi` (LangChain-heavy — don't copy its deps), `api_graphql`, `mdr_restapi`, or `semantic_search_mcp_server`. Copy boilerplate (`.dockerignore`, `.gitignore`, `build.sh`, `build-docker.sh`, `Dockerfile2`) verbatim; **never** copy the dependency block wholesale.
4. **Multi-layer?** If the service has non-trivial reusable logic (a new component), spawn an Opus `Plan` agent and **confirm the plan with the user** before writing code.

## Build steps (mirror the guide's Steps 1–7)

### 1. Base — `bases/lif/<service>/`
`__init__.py` (exposes `core`), `core.py` (FastAPI app), one or more `*_endpoints.py` route modules.
- **Logger consistency:** `from lif.logging import get_logger` throughout. Do **not** mix in `lif.mdr_utils.logger_config` (different format).
- **Auth:** internal-only services use `AuthMiddleware` from `lif.mdr_auth.core` — don't reinvent JWT/API-key handling.
- `/health-check` returns `HealthCheckResponse` and is in the public allowlist.

### 2. Project — `projects/lif_<service>/`
`pyproject.toml`, `Dockerfile2`, `build.sh`, `build-docker.sh`, `README.md`.
- **Trim dependencies to what you actually import.** A REST API usually needs only `fastapi` + `uvicorn` (+ `httpx`/`pyjwt`/a SQL driver if used). **Do not** pull in `langchain`/`langgraph`/`mcp`/`torch` unless the service genuinely uses them — that bloats the image by hundreds of MB.
- **PEP 440 `~=` gotcha:** `~=0.275` means `>= 0.275, < 1.0`. To pin a minor range write `~=0.275.0`. (This caused a past prod crash — see CLAUDE.md.)
- **Docker resolves deps from *this project's* `pyproject.toml`, not `uv.lock`.** A dep declared only at the monorepo root is **absent in the image** (the `boto3` landmine). Declare it here.
- `Dockerfile2`: copy verbatim, change only `PROJECT_NAME`, the `--port`, and the uvicorn target.

### 3. `[tool.polylith.bricks]` — must match actual imports
List only the bricks your code imports. After the code is written, verify:
```bash
grep -rhn '^from lif\.' bases/lif/<service>/ | sort -u
```
Every `lif.X` import needs a matching brick line; every brick line needs ≥1 import. No dead entries.
- **If a Dagster job will use a new component**, add it to `[tool.polylith.bricks]` in **all three** `projects/dagster_*/pyproject.toml` files (per CLAUDE.md), not just the orchestrator.

### 4. Auth wiring (if internal-only)
- Add `mdr__auth__service_api_key__<service>` to `components/lif/mdr_utils/config.py`.
- Add it to the `API_KEYS` dict in `components/lif/mdr_auth/core.py` (server-side accept-list — every `AuthMiddleware` service will accept it).

### 5. docker-compose — `deployments/advisor-demo-docker/docker-compose.yml`
Follow an existing service block: env vars (CORS, `MDR__AUTH__*`, the allowlist for `/health-check` + `/docs`), the chosen port, network(s), and a `/health-check` healthcheck. Don't list service-API-key env vars your service doesn't actually call with.

### 6. CI + CloudFormation
- **GitHub Actions:** copy `.github/workflows/lif_advisor_api.yml`; set the `paths:` triggers to your project/base/components. Remember **feature branches don't auto-deploy** — dev `:latest` rebuilds only on push-to-main or manual `workflow_dispatch`.
- **CloudFormation:** add a template under `cloudformation/`, register the stack in `dev.aws` and `demo.aws` (`STACKS` + `STACK_ORDER`). **If this is your first stack, ask the user for a pairing session** — ALB listener priorities and SSM paths are easy to get wrong solo.

### 7. Tests — mirror under `test/`
At minimum (use `httpx.AsyncClient(transport=ASGITransport(app=app), ...)` in-process — see `test/bases/lif/mdr_restapi/test_tenant_endpoints.py` for the `get_session` override + auth-stub pattern):
- health-check returns 200 **without** auth
- an authenticated endpoint returns 401 **without** a key
- the happy path returns its payload **with** a valid key

## Verify before opening the PR

Run the `test` skill, or at minimum:
```bash
uv run ruff check && uv run ruff format --check && uv run ty check
uv run poly check
uv run pytest test/bases/lif/<service>/
```
Then walk the guide's final checklist (base / project / trimmed deps / brick match / logger consistency / allowlist / auth key / compose / CI / CFN / tests / green checks). Commit with `Issue #XXX: <description>` (the commit convention).
