# Scripts

Utility scripts for managing deployments, credentials, and data. All AWS scripts require `AWS_PROFILE=lif` and default to **dry-run** mode — pass `--apply` to make changes.

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

## Common Patterns

Most AWS scripts follow the same conventions:

```bash
# Dry-run (preview what will happen)
AWS_PROFILE=lif ./scripts/<script>.sh <env>

# Apply changes
AWS_PROFILE=lif ./scripts/<script>.sh <env> --apply
```

Where `<env>` is `dev` or `demo`.
