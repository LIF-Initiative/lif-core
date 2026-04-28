# Updating the Demo Environment

This guide walks through the end-to-end process of promoting the current dev build to the demo environment. It covers updating image tags in CloudFormation parameter files, deploying the ECS service stacks, deploying the MDR frontend, and updating the SAM-managed databases.

## Prerequisites

- AWS CLI v2 configured with the `lif` profile (or the appropriate AWS profile)
- AWS SSO session active (the deploy script will prompt for login if needed)
- Bash 4+
- `jq`
- `docker`
- Node.js 20+ and `npm` (for MDR frontend build)
- [yq](https://github.com/mikefarah/yq)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)

All commands below are run from the **repository root**.

## Step 0: Ensure SSM parameters exist

Several services read secrets from AWS SSM Parameter Store at startup. If these parameters are missing, the ECS tasks will fail to launch. This step only needs to be done once per environment (or when adding new services).

### MDR API keys

The MDR API authenticates requests from GraphQL, semantic search, and translator services using shared API keys. Each key is stored on both the server side (MDR API) and client side (the calling service).

The `setup-mdr-api-keys.sh` script generates keys and stores them in all the right places:

```bash
# Preview what will be created
AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo

# Create missing keys (skips existing, fixes mismatches)
AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo --apply

# Regenerate all keys (overwrites existing)
AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo --apply --force
```

The script manages these parameters:

| Key group | Server parameter (MDR API) | Client parameter(s) |
|-----------|---------------------------|---------------------|
| GraphQL | `/{env}/mdr-api/MdrAuthServiceApiKeyGraphql` | `/{env}/graphql-org{1,2,3}/MdrApiKey` |
| Semantic Search | `/{env}/mdr-api/MdrAuthServiceApiKeySemanticSearch` | `/{env}/semantic-search/MdrApiKey` |
| Translator | `/{env}/mdr-api/MdrAuthServiceApiKeyTranslator` | `/{env}/translator-org1/MdrApiKey` |

After creating or rotating keys, restart affected services to pick up the new values:

```bash
./aws-deploy.sh -s demo --update-ecs
```

### GraphQL API keys (external access)

GraphQL services also require an `ApiKeys` SSM parameter for external API key authentication. For internal-only instances, create the parameter with a blank value to disable auth while still allowing the task to start:

```bash
AWS_PROFILE=lif aws ssm put-parameter --name "/demo/graphql-org1/ApiKeys" --value " " --type SecureString --overwrite
AWS_PROFILE=lif aws ssm put-parameter --name "/demo/graphql-org2/ApiKeys" --value " " --type SecureString --overwrite
AWS_PROFILE=lif aws ssm put-parameter --name "/demo/graphql-org3/ApiKeys" --value " " --type SecureString --overwrite
```

To enable external access on a specific instance, set the value to comma-separated `key:name` pairs:

```bash
AWS_PROFILE=lif aws ssm put-parameter --name "/demo/graphql-org1/ApiKeys" --value "mykey123:client-name" --type SecureString --overwrite
```

See `cloudformation/README.md` for full details on enabling public GraphQL access.

## Step 1: Update image tags in param files

The `release-demo.sh` script reads every `cloudformation/demo-*.params` file that contains an `ImageUrl` parameter, queries ECR for the image currently tagged `latest` in each repository, resolves its version tag, and updates the param file.

### 1a. Preview changes (dry-run)

```bash
AWS_PROFILE=lif ./scripts/release-demo.sh
```

This shows which files would change and what the new tags would be. No files are modified.

### 1b. Apply changes

```bash
AWS_PROFILE=lif ./scripts/release-demo.sh --apply
```

Review the output to confirm all files updated successfully. Any failures are listed in the summary.

### 1c. Review the diff

```bash
git diff cloudformation/demo-*.params
```

Verify the changes look correct — each `ImageUrl` should now reference a specific timestamped tag (e.g., `2026-02-04-01-54-13-e86843d`) rather than the previous tag.

## Step 2: Deploy CloudFormation stacks

The `aws-deploy.sh` script uploads templates and param files to S3, then creates or updates each CloudFormation stack in dependency order as defined in `demo.aws`.

### 2a. Deploy all stacks

```bash
./aws-deploy.sh -s demo
```

This deploys all 34 stacks in order:

1. **Base infrastructure** — repositories, networking, common services
2. **Org1 services** — translator, identity-mapper, mongodb, query-cache, query-planner, graphql, semantic-search, advisor-api, advisor-app, example-data-source
3. **Org2 services** — identity-mapper, mongodb, query-cache, query-planner, graphql
4. **Org3 services** — identity-mapper, mongodb, query-cache, query-planner, graphql
5. **Shared services** — orchestrator-api, mdr-frontend, mdr-api
6. **Dagster** — code-location, webserver, daemon

Each stack updates the ECS task definition with the new image tag. ECS then performs a rolling deployment of the new container image.

### 2b. Deploy a single stack (optional)

To update just one service:

```bash
./aws-deploy.sh -s demo --only-stack demo-lif-graphql-org1
```

### 2c. Force ECS redeployment (optional)

If CloudFormation shows no changes (the task definition didn't change) but you need to force containers to restart:

```bash
./aws-deploy.sh -s demo --update-ecs
```

This calls `aws ecs update-service --force-new-deployment` on every service in the `demo` cluster.

## Step 3: Deploy MDR frontend

The MDR frontend is a static Vite/React app hosted on S3 + CloudFront — not an ECS service. It is deployed separately using `release-demo-frontend.sh`, which builds from a specific git ref and syncs the output to the demo S3 bucket.

### 3a. Preview (dry-run)

```bash
AWS_PROFILE=lif ./scripts/release-demo-frontend.sh main
```

This resolves the git ref, shows the commit SHA, target S3 bucket, and API URL, then exits without building or deploying.

### 3b. Build and deploy

```bash
AWS_PROFILE=lif ./scripts/release-demo-frontend.sh main --apply
```

You can use any git ref — a branch name, tag, or commit SHA:

```bash
AWS_PROFILE=lif ./scripts/release-demo-frontend.sh v1.2.0 --apply
AWS_PROFILE=lif ./scripts/release-demo-frontend.sh abc1234 --apply
```

The script:

1. Creates a temporary git worktree at the specified ref (does not disturb your working tree)
2. Runs `npm ci` and `npm run build` with `VITE_API_URL` pointing to the demo MDR API
3. Syncs the built `dist/` directory to the demo S3 bucket
4. Invalidates the CloudFront distribution so the new version is served immediately
5. Cleans up the temporary worktree

## Step 4: Update SAM databases (if needed)

The MDR and Dagster databases are managed separately via AWS SAM. This step is only needed when there are Flyway migration changes (new SQL files in `sam/*/flyway/`).

### 4a. Deploy both databases

```bash
./aws-deploy.sh -s demo --update-sam
```

This iterates over the `SAM_STACKS` array in `demo.aws` (`mdr-database`, `dagster-database`) and runs `deploy-sam.sh` for each.

### 4b. Deploy a single database directly

```bash
cd sam && bash deploy-sam.sh -s ../demo -d mdr-database
cd sam && bash deploy-sam.sh -s ../demo -d dagster-database
```

Each SAM deploy:

1. Builds the Flyway Docker image (bundling any new SQL migration files)
2. Pushes it to ECR with a timestamped tag
3. Runs `sam deploy`, which updates the CloudFormation stack
4. The changed `pImageTag` triggers the Flyway Lambda via a CloudFormation custom resource
5. Flyway runs `migrate`, applying only pending versioned migrations

See `sam/README.md` for details on the migration mechanism and how to add new SQL files.

### 4c. Reset the MDR database (when V1.1 is replaced)

When `V1.1__metadata_repository_init.sql` is **replaced** (not a new V1.2 added), Flyway won't re-run it because it's already marked as applied. The database must be cleaned and re-migrated from scratch.

**WARNING:** This destroys all data in the MDR database.

```bash
# Preview
AWS_PROFILE=lif ./scripts/reset-mdr-database.sh demo

# Execute
AWS_PROFILE=lif ./scripts/reset-mdr-database.sh demo --apply
```

The script automates what was previously a manual process:

1. Builds the Flyway Docker image with the updated SQL files
2. Pushes to ECR
3. Updates the Lambda function to use the new image
4. Waits for the Lambda update to complete
5. Invokes the Lambda with a `Reset` payload (`flyway clean` + `flyway migrate`)
6. Runs the full SAM deploy to sync CloudFormation state

## Step 5: Commit and create PR

After verifying the deployment is healthy:

```bash
git add cloudformation/demo-*.params
git commit -m "Issue #XXX: Update demo image tags to match dev"
```

Create a PR so the pinned image tags are tracked in version control.

## Quick Reference

| What | Command |
|------|---------|
| Audit MDR API keys | `AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo` |
| Create missing MDR API keys | `AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo --apply` |
| Preview image tag updates | `AWS_PROFILE=lif ./scripts/release-demo.sh` |
| Apply image tag updates | `AWS_PROFILE=lif ./scripts/release-demo.sh --apply` |
| Deploy all stacks | `./aws-deploy.sh -s demo` |
| Deploy one stack | `./aws-deploy.sh -s demo --only-stack <stack-name>` |
| Force ECS redeployment | `./aws-deploy.sh -s demo --update-ecs` |
| Preview MDR frontend deploy | `./scripts/release-demo-frontend.sh <git-ref>` |
| Deploy MDR frontend | `./scripts/release-demo-frontend.sh <git-ref> --apply` |
| Deploy SAM databases | `./aws-deploy.sh -s demo --update-sam` |
| Deploy MDR database only | `cd sam && bash deploy-sam.sh -s ../demo -d mdr-database` |
| Deploy Dagster database only | `cd sam && bash deploy-sam.sh -s ../demo -d dagster-database` |
| Reset MDR database (V1.1 replaced) | `./scripts/reset-mdr-database.sh demo --apply` |

## Troubleshooting

### `scripts/release-demo.sh` reports ECR access denied
Ensure your AWS session is active and targeting the correct account:
```bash
AWS_PROFILE=lif aws sts get-caller-identity
```

### `scripts/release-demo.sh` reports "No image tagged 'latest'"
The dev CI pipeline tags the most recent build as `latest`. If a repository has no `latest` tag, the dev build may not have completed successfully for that service.

### ECS task fails to start with "missing SSM parameter"
A required SSM parameter doesn't exist. Run the MDR API key setup script to check for missing parameters:
```bash
AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo
```
Also verify the GraphQL `ApiKeys` parameters exist (see Step 0). If a service references an SSM parameter that doesn't exist, the ECS task definition cannot be created and the container won't start.

### CloudFormation stack stuck in `UPDATE_IN_PROGRESS`
The `cfn-wait.sh` script polls until completion. If a stack is stuck, check the CloudFormation console for event details. Common causes: ECS health check failures, container crash loops, or insufficient permissions.

### MDR frontend build fails
Ensure Node.js 20+ is installed (`node --version`). The build requires `npm ci` to succeed, which needs a valid `package-lock.json` at the specified git ref. If the ref is very old, the frontend directory structure may differ.

### Flyway migration fails
Check the Flyway Lambda logs in CloudWatch (`/aws/lambda/{env}-{user}-flyway`). Common causes: SQL syntax errors in a new migration file, or a migration that conflicts with the current database state.

### SAM stack stuck in `UPDATE_ROLLBACK_FAILED`
If a SAM deploy fails (e.g., the Flyway Lambda trigger times out), the nested CloudFormation stack may end up in `UPDATE_ROLLBACK_FAILED`. To recover:

```bash
# Run continue-update-rollback on the parent stack, skipping the stuck resource in the nested stack
AWS_PROFILE=lif aws cloudformation continue-update-rollback \
  --stack-name demo-lif-mdr-db-resources \
  --resources-to-skip "demo-lif-mdr-db-resources-MDRDatabase-<NESTED_ID>.FlywayLambdaFnTrigger"
```

Find the nested stack ID in the CloudFormation console or with `aws cloudformation list-stacks --stack-status-filter UPDATE_ROLLBACK_FAILED`. Once both stacks reach `UPDATE_ROLLBACK_COMPLETE`, you can re-run the SAM deploy.

### MDR database reset step 6 fails
The reset script (`reset-mdr-database.sh`) has 6 steps. Steps 1–5 (build, push, update Lambda, wait for update, invoke reset) can succeed while step 6 (SAM deploy to sync CloudFormation state) fails independently. If this happens:

1. The database itself is fine — the reset already completed in step 5
2. Resolve the CloudFormation stack state (see above if stuck in `UPDATE_ROLLBACK_FAILED`)
3. Re-run just the SAM deploy to sync state:
   ```bash
   cd sam && bash deploy-sam.sh -s ../demo -d mdr-database
   ```
