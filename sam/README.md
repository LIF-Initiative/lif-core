# SAM Database Deployments

This directory contains AWS SAM applications for provisioning and migrating the project's Aurora PostgreSQL databases. Each subdirectory is a self-contained SAM application that creates an Aurora cluster and applies schema migrations via Flyway.

| Directory | Database | IAM User | Purpose |
|-----------|----------|----------|---------|
| `mdr-database/` | `{env}MdrDb` | `mdr` | Metadata Registry — stores the LIF data model, value sets, transformations, and schema metadata |
| `dagster-database/` | `{env}DagsterDb` | `dagster` | Dagster storage — run history, event log, and schedule state for the orchestration layer |

## How It Works

Both databases share the same architecture and deployment mechanism. The only differences are the database name, IAM user, and SQL migration files.

### Infrastructure (CloudFormation)

```
template.yaml          Top-level SAM template; creates a nested stack from aurora-postgres.yml
aurora-postgres.yml    Shared nested template that provisions:
                         - Aurora PostgreSQL cluster (engine 17.4)
                         - DB subnet group, security groups, DNS record
                         - Secrets Manager secret for the master password
                         - SSM parameters for host, port, username, password, DB name
                         - CloudWatch alarms and SNS topic (when pCreateAlarms=True)
                         - Flyway Lambda functions (see below)
                         - Read replica (pre-prod and prod only)
```

### Schema Migrations (Flyway)

Schema changes are managed by [Flyway](https://flywaydb.org/) running inside a Docker-based Lambda function.

#### Migration files

```
flyway/flyway-files/flyway/sql/<iam-user>/
```

| Database | Current migrations |
|----------|-------------------|
| MDR | `V1.0__database_init.sql` — Extensions, IAM role, grants |
|     | `V1.1__metadata_repository_init.sql` — Full schema and seed data (~2 MB pg_dump) |
| Dagster | `V1.0__database_init.sql` — Extensions, IAM role, grants (Dagster manages its own schema at runtime) |

Flyway tracks which migrations have already been applied. On each deploy it runs only the new ones.

#### Lambda execution model

Two Lambda functions work together to run migrations:

1. **Flyway Lambda** (`{env}-{user}-flyway`) — A Docker image built from `flyway/Dockerfile` (based on `flyway/flyway:11.12`). Runs inside the VPC with access to the Aurora cluster. On invocation it:
   - Fetches DB credentials from Secrets Manager (`MASTER_SECRET_ARN`)
   - Runs `flyway migrate` against the versioned SQL files
   - Supports a `Reset` request type that runs `flyway clean` first (destroys all objects)

2. **Invoker Lambda** (`{env}-{user}-flyway-invoker`) — A Node.js function (`customResourceFn/customInvoker.ts`) that runs outside the VPC. It acts as a bridge between CloudFormation and the VPC-bound Flyway Lambda, since CloudFormation custom resources cannot signal back through IPv6-only VPCs without a NAT gateway.

#### Trigger mechanism

A CloudFormation custom resource triggers migrations on every deploy:

```yaml
FlywayLambdaFnTrigger:
  Type: Custom::FlywayTrigger
  Properties:
    ServiceToken: !GetAtt FlywayLambdaInvokerFn.Arn
    TargetFunctionName: !Sub ${pEnv}-${IamUser}-flyway
    pImageTag: !Ref pImageTag      # Changing this triggers an Update event
```

The `pImageTag` parameter is set to a timestamp on each deploy. Because the value changes, CloudFormation treats it as an Update, which invokes the Invoker Lambda, which calls the Flyway Lambda, which runs `flyway migrate`.

## Deploying

### Prerequisites

- AWS CLI configured with appropriate credentials
- Docker
- [yq](https://github.com/mikefarah/yq)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)

> **Apple Silicon note:** The Flyway Lambda runs on x86_64. Both `deploy-sam.sh` and `reset-mdr-database.sh` build with `--platform linux/amd64` so images are correct regardless of the host architecture.

### Commands

From the repository root:

```bash
# MDR database
cd sam && bash deploy-sam.sh -s mdr-database/dev -d mdr-database      # dev
cd sam && bash deploy-sam.sh -s mdr-database/demo -d mdr-database     # demo

# Dagster database
cd sam && bash deploy-sam.sh -s dagster-database/dev -d dagster-database      # dev
cd sam && bash deploy-sam.sh -s dagster-database/demo -d dagster-database     # demo
```

The `deploy-sam.sh` script:

1. Sources environment config from `{env}.aws` (sets AWS region, SAM config env)
2. Builds the Flyway Docker image and pushes it to ECR with a timestamped tag
3. Runs `sam build`
4. Runs `sam deploy` with `pImageTag=<timestamp>`, triggering the Flyway migration

### Environment configuration

Each database directory contains:

| File | Purpose |
|------|---------|
| `samconfig.yaml` | SAM CLI config per environment (stack name, region, parameter overrides) |
| `dev.dockerImages` | Maps ECR repo name to Docker build directory for dev |
| `demo.dockerImages` | Maps ECR repo name to Docker build directory for demo |

The `.aws` files (not checked in) provide `AWS_REGION` and `SAM_CONFIG_ENV`.

## Updating a Database Schema

### MDR database

1. Add a new versioned SQL file:
   ```
   sam/mdr-database/flyway/flyway-files/flyway/sql/mdr/V1.2__your_description.sql
   ```
2. Deploy:
   ```bash
   cd sam && bash deploy-sam.sh -s mdr-database/<env> -d mdr-database
   ```
3. The deploy rebuilds the Flyway Docker image (bundling the new SQL file), pushes it to ECR, and the CloudFormation update triggers Flyway to apply pending migrations.

### MDR database — replacing V1.1 (full reset)

When `V1.1__metadata_repository_init.sql` is **replaced** rather than adding a new version, a standard deploy won't work — Flyway sees V1.1 as already applied and skips it. The database must be cleaned and re-migrated from scratch.

Use the reset script from the repository root:

```bash
# Preview
AWS_PROFILE=lif ./scripts/reset-mdr-database.sh <env>

# Execute (WARNING: destroys all MDR data)
AWS_PROFILE=lif ./scripts/reset-mdr-database.sh <env> --apply
```

The script:

1. Builds the Flyway Docker image with the updated SQL files
2. Pushes it to ECR
3. Updates the Lambda function to use the new image
4. Waits for the Lambda update to complete
5. Invokes the Lambda with a `Reset` payload (runs `flyway clean` then `flyway migrate`)
6. Runs the full SAM deploy to sync the CloudFormation state with the new image tag

### Dagster database

Dagster manages its own schema at runtime (run storage, event log, schedule storage tables). The only Flyway migration (`V1.0`) bootstraps the database with extensions and the IAM role. You would typically not add Flyway migrations here unless you need to create custom extensions or roles beyond what Dagster manages.

If you do need a migration:

1. Add a new versioned SQL file:
   ```
   sam/dagster-database/flyway/flyway-files/flyway/sql/dagster/V1.2__your_description.sql
   ```
2. Deploy:
   ```bash
   cd sam && bash deploy-sam.sh -s dagster-database/<env> -d dagster-database
   ```
