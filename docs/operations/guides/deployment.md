# Deployment & Operations

Deployment scripts, environment config, MDR migrations, and debugging runbooks. For the full demo-promotion walkthrough see [`demo-environment-update.md`](demo-environment-update.md); for SAM/database details see [`sam/README.md`](../../../sam/README.md).

## Environment Configuration
- `{env}.aws` files (repo root) — define `AWS_REGION`, `SAM_CONFIG_ENV`, `STACKS` map, and `STACK_ORDER` for each environment
- `cloudformation/{env}-*.params` — CloudFormation parameter files per stack, including `ImageUrl` for ECS services
- Environments: `dev`, `demo` (demo is manually promoted from dev)

## Deployment Scripts

| Script | Purpose |
|--------|---------|
| `aws-deploy.sh` | Deploy CloudFormation stacks (`-s demo`, `--only-stack`, `--update-ecs`, `--update-sam`) |
| `scripts/release-demo.sh` | Update demo param files with latest ECR image tags from dev |
| `scripts/release-demo-frontend.sh` | Build and deploy MDR frontend to S3/CloudFront from a git ref |
| `scripts/verify-demo-images.sh` | Compare param file image tags against running ECS tasks |
| `scripts/setup-mdr-api-keys.sh` | Generate and store MDR service API keys in SSM Parameter Store |
| `scripts/setup-graphql-api-keys.sh` | Generate and store GraphQL org1 API keys in SSM (service + workshop modes) |
| `scripts/reset-mdr-database.sh` | Reset MDR database (flyway clean + migrate) when V1.1 SQL is replaced |
| `sam/deploy-sam.sh` | Build Flyway Docker image, push to ECR, run SAM deploy for database stacks |

## Environment Differences
- **Dev** uses `:latest` ECR image tags in param files; **demo** uses pinned version tags (e.g., `:1.2.3`)
- `scripts/release-demo.sh` copies the current dev image tags to demo param files for promotion
- Dev has a single-org setup (`dev-single-org`); demo has multi-org (`advisor-demo-org1/2/3`)

## MDR Schema Migrations (V1.2+)

- **Deployed envs** run migrations via Flyway (tracked in `flyway_schema_history`).
- **Local docker-compose** loads `backup.sql` (a pg_dump snapshot of V1.1 content) and then runs every `V1.*.sql` file in the Flyway directory through `psql` — it does *not* use real Flyway and does *not* track history. See `projects/lif_mdr_database/restore.sh`.
- This only re-runs on first init (empty data dir) or after `docker compose down -v`. Persistent-volume `up`/`down` cycles are safe.
- **Authoring convention:** every V1.2+ migration must be idempotent so local re-init is safe. Use `CREATE OR REPLACE FUNCTION`, `CREATE TABLE IF NOT EXISTS`, `DROP TRIGGER IF EXISTS … CREATE TRIGGER`, etc. rather than raw `CREATE`. This is a local-dev concession; deployed envs would tolerate non-idempotent migrations via Flyway's history tracking, but we keep one style across both.
- Wiring real Flyway into local docker-compose is a known gap; deferred pending the broader MDR database tooling evaluation (`docs/proposals/mdr-mongodb-evaluation.md`).

## Key Operational Notes
- **Demo update guide**: See [`demo-environment-update.md`](demo-environment-update.md) for the full end-to-end process
- **SAM databases**: See `sam/README.md` for database deployment architecture and Flyway migration details
- **Apple Silicon**: Docker images for Lambda must use `--platform linux/amd64` (already handled in scripts)
- **SSM parameters**: ECS tasks fail to start if referenced SSM parameters are missing, even optional ones like `ApiKeys`
- **Deploy sequentially**: Running multiple `aws-deploy.sh` commands in parallel causes SSO login conflicts
- **MDR frontend**: Deployed to S3 + CloudFront (not ECS); use `scripts/release-demo-frontend.sh` for demo
- **Bash `grep -v` with `pipefail`**: In scripts using `set -o pipefail`, `grep -v` returns exit code 1 when all lines are filtered out (no matches). Wrap in `(grep -v ... || true)` to prevent script failure.

## Docker Build Dependency Resolution (IMPORTANT)

Project Dockerfiles (`projects/*/Dockerfile2`) build wheels independently from the monorepo lock file. The runtime stage installs the wheel with `uv pip install --system`, which resolves dependencies from PyPI based on the wheel's metadata constraints — **not** from `uv.lock`. This means Docker images can get different dependency versions than local development.

**PEP 440 `~=` gotcha**: `~=0.275` means `>= 0.275, < 1.0`, NOT `>= 0.275, < 0.276`. To constrain to a minor version range, use `~=0.275.0` (which means `>= 0.275.0, < 0.276.0`). This distinction caused a production crash when `strawberry-graphql~=0.275` resolved to `0.297.0` in Docker.

## Debugging ECS Services

**CloudWatch log group**: All dev ECS services share a single log group named `dev`. Log streams are prefixed by service name (e.g., `graphql-org1/graphql-org1/<task-id>`).

```bash
# Tail recent logs for a service
AWS_PROFILE=lif AWS_REGION=us-east-1 aws logs filter-log-events \
  --log-group-name dev --log-stream-name-prefix graphql-org1 \
  --start-time $(python3 -c "import time; print(int((time.time()-3600)*1000))") \
  --limit 100 --query 'events[].message' --output text

# Filter for errors only
AWS_PROFILE=lif AWS_REGION=us-east-1 aws logs filter-log-events \
  --log-group-name dev --log-stream-name-prefix graphql-org1 \
  --filter-pattern "ERROR" --limit 20 --query 'events[].message' --output text

# Check service status and recent events
AWS_PROFILE=lif AWS_REGION=us-east-1 aws ecs describe-services \
  --cluster dev --services graphql-org1-FARGATE \
  --query 'services[0].{status:status,running:runningCount,events:events[:3]}'
```

**ECS Exec** is enabled on dev services but requires the Session Manager Plugin (`session-manager-plugin`) installed locally.

## Querying the MDR API

The MDR API provides the OpenAPI schema that GraphQL services load at startup. Useful for debugging schema-related issues.

```bash
# Get the MDR API key for a service (stored in SSM)
AWS_PROFILE=lif AWS_REGION=us-east-1 aws ssm get-parameter \
  --name /dev/graphql-org1/MdrApiKey --with-decryption \
  --query 'Parameter.Value' --output text

# Fetch the OpenAPI schema (data model ID 17 for dev)
curl -s -H "X-API-Key: <key>" \
  "https://mdr-api.dev.lif.unicon.net/datamodels/open_api_schema/17?include_attr_md=true&include_entity_md=false"
```

**MDR auth uses `X-API-Key` header** (not Bearer token). The endpoint path is `/datamodels/open_api_schema/{data_model_id}`.
