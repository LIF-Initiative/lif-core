# Scripts

Utility scripts for managing deployments, credentials, and data. AWS scripts require `AWS_PROFILE=lif`. Scripts that **mutate** state default to **dry-run** mode and require `--apply` to make changes; read-only scripts (e.g. `export_cognito_registrations.py`, `verify-demo-images.sh`) take no `--apply` and run directly.

## AWS Authentication

| Script | Purpose |
|--------|---------|
| `login.sh` | Authenticate to AWS via SSO. **Must be sourced** (`source ./login.sh`), not executed, so credentials persist in the current shell. |

## CloudFormation

| Script | Purpose |
|--------|---------|
| `cfn-deploy.sh` | Deploy or update a CloudFormation stack via change set. Supports `--changeset-only` for review before execution. |
| `cfn-wait.sh` | Poll a CloudFormation stack until it reaches a terminal state, printing progress events. Usage: `./cfn-wait.sh <stack-name> <region>` |
| `init-stack-params.sh` | Initialize CloudFormation parameter files for an environment. Sources `{env}.aws` for configuration. |

## Credential & Key Management

| Script | Purpose |
|--------|---------|
| `setup-mdr-api-keys.sh` | Generate and store MDR service API keys in SSM. Use `--force` to regenerate existing keys. |
| `setup-graphql-api-keys.sh` | Manage GraphQL org1 API keys in SSM. Supports service keys and temporary keys (`--temporary <count>`) for workshops. |
| `setup-demo-user-password.sh` | Store a shared demo user password in SSM (reads interactively, never echoed). Creates params for both advisor-api and mdr-api. |

## Configuration Sync

| Script | Purpose |
|--------|---------|
| `sync-query-planner-config.sh` | Sync Query Planner `information_sources_config` YAML files from the repo to SSM. Use `--org <org>` to target a single org. |

## Database

| Script | Purpose |
|--------|---------|
| `reset-mdr-database.sh` | **Destructive.** Wipes and recreates the MDR database via Flyway clean + migrate. Required when `V1.1__metadata_repository_init.sql` is replaced rather than versioned incrementally. |
| `provision-mdr-tenant.sh` | Create a `tenant_{name}` PostgreSQL schema by cloning DDL (and optionally data) from `public`. Supports MDR self-serve multi-tenancy (issue #883). Uses libpq env vars (`PG*`) for connectivity — caller manages network access. |
| `backfill-transformation-group-activation.sh` | One-time backfill for #1350: dates the highest undated version of each transformation group pair and deprecates the older ones (dated or not), so each pair ends with one active row, in `public` and every `tenant_*` schema. Dry-run by default (runs and rolls back), `--apply` to commit; idempotent. Uses libpq env vars (`PG*`). |
| `backfill_transformation_group_activation.py` | The same backfill through `asyncpg`, for hosts without `psql` (the `mdr-api` container via ECS exec). Runs the shell script's SQL unchanged (a test keeps them equal). Uses the MDR's `POSTGRESQL_*` env vars. |
| `check_transformation_group_activation.py` | Read-only gate for #1350 before the Translator switches to the active-mapping endpoint: reports each transformation group pair in `public` and every `tenant_*` schema as `ok` (one active version), `retired` (every version deprecated; expected), or `FAIL`, and exits 1 if any pair fails. Uses the MDR's `POSTGRESQL_*` env vars, so it runs in the `mdr-api` container via ECS exec. |
| `measure_overlay_conversion.py` | Read-only sizing for #1388: for each overlay model in `public` and every `tenant_*` schema, counts what converting it to a self-contained model would touch (inclusion rows, overrides, `UniqueName` clashes, value sets, `ExtendedBy` links, unassociated attributes, and the mapping rows to re-point). Changes nothing. Uses the MDR's `POSTGRESQL_*` env vars, so it runs in the `mdr-api` container via ECS exec. |
| `measure_export_blockers.py` | Read-only count for #1393 of what keeps each model and mapping group from exporting as a portable file: runs `export_model` and `export_mapping_group` on every live model and group in `public` and every `tenant_*` schema, and counts each refusal reason with the models or groups it names. Overlays are listed apart (#1388). Changes nothing. Needs the MDR API's packages and `POSTGRESQL_*` env vars, so it runs in the `mdr-api` container via ECS exec. |
| `cleanup_export_blockers.py` | One-time cleanup for #1393 of the data that keeps models and mapping groups from exporting, by the rules decided there: soft-delete unassociated attributes (skipping any a live mapping row uses), set a NULL `DataType` to `string`, name blank groups `<source>_<target>`, set model 26's organization to `LIF`, soft-delete transformation 1189, and clear the stray `Extension` flag on value 3649. Overlays are left to #1388. One transaction across `public` and every `tenant_*` schema; prints the Ids it changed and rolls back unless `--apply`. Uses the MDR's `POSTGRESQL_*` env vars, so it runs in the `mdr-api` container via ECS exec. |

## Demo Release

| Script | Purpose |
|--------|---------|
| `release-demo.sh` | Update demo CloudFormation parameter files with the latest image tags from dev ECR. Queries ECR for each `latest`-tagged image and resolves its version tag. |
| `release-demo-frontend.sh` | Build the MDR frontend from a specific git ref and deploy to the demo S3 bucket + CloudFront. Usage: `./scripts/release-demo-frontend.sh <git-ref> --apply` |
| `verify-demo-images.sh` | Compare image tags in demo param files against what is actually running in the demo ECS cluster. Reports matches, mismatches, and services not running. |

## ECS Operations

| Script | Purpose |
|--------|---------|
| `exec.sh` | Open an interactive shell in a running Fargate container via ECS Exec. Requires `-s <env>` (sources `{env}.aws` for cluster config). |

## Sample Data Generation

| Script | Purpose |
|--------|---------|
| `generate_sample_users.py` | Generate synthetic sample user JSON files across all three demo orgs. See [README_sample_users.md](README_sample_users.md) for details. |
| `fix_sample_data_schema.py` | Validate and fix sample data files to conform to the current LIF schema. Adds missing required fields. Use `--dry-run` to preview. |

## Self-Serve Operations

| Script | Purpose |
|--------|---------|
| `export_cognito_registrations.py` | Export the self-serve User Pool's users (with `custom:organization`, `custom:role`, `custom:reason`, status, signup date, group membership) for outreach. Read-only — no `--apply` needed. Run via `uv run`; reads UserPoolId from the `{env}-lif-mdr-cognito` stack output. Flags: `--format` (`csv` or `json`, default `csv`), `--output <path>` to write to file (default stdout), `--region <r>` overrides AWS region (defaults to `$AWS_REGION`, then `$AWS_DEFAULT_REGION`, then `us-east-1`). |

## Common Patterns

Most AWS scripts follow the same conventions:

```bash
# Dry-run (preview what will happen)
AWS_PROFILE=lif ./scripts/<script>.sh <env>

# Apply changes
AWS_PROFILE=lif ./scripts/<script>.sh <env> --apply
```

Where `<env>` is `dev` or `demo`.
