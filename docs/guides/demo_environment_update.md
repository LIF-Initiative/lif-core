# Updating the Demo Environment

This guide walks through the end-to-end process of promoting the current dev build to the demo environment. It covers updating image tags in CloudFormation parameter files, deploying the ECS service stacks, deploying the MDR frontend, and updating the SAM-managed databases.

## Prerequisites

- AWS CLI v2 configured with the `lif` profile (or the appropriate profile for account `381492161417`)
- AWS SSO session active (the deploy script will prompt for login if needed)
- Bash 4+
- `jq`
- `docker`
- Node.js 20+ and `npm` (for MDR frontend build)
- [yq](https://github.com/mikefarah/yq)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)

All commands below are run from the **repository root**.

## Step 1: Update image tags in param files

The `release-demo.sh` script reads every `cloudformation/demo-*.params` file that contains an `ImageUrl` parameter, queries ECR for the image currently tagged `latest` in each repository, resolves its version tag, and updates the param file.

### 1a. Preview changes (dry-run)

```bash
AWS_PROFILE=lif ./release-demo.sh
```

This shows which files would change and what the new tags would be. No files are modified.

### 1b. Apply changes

```bash
AWS_PROFILE=lif ./release-demo.sh --apply
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
AWS_PROFILE=lif ./release-demo-frontend.sh main
```

This resolves the git ref, shows the commit SHA, target S3 bucket, and API URL, then exits without building or deploying.

### 3b. Build and deploy

```bash
AWS_PROFILE=lif ./release-demo-frontend.sh main --apply
```

You can use any git ref — a branch name, tag, or commit SHA:

```bash
AWS_PROFILE=lif ./release-demo-frontend.sh v1.2.0 --apply
AWS_PROFILE=lif ./release-demo-frontend.sh abc1234 --apply
```

The script:

1. Creates a temporary git worktree at the specified ref (does not disturb your working tree)
2. Runs `npm ci` and `npm run build` with `VITE_API_URL` pointing to the demo MDR API
3. Syncs the built `dist/` directory to `s3://demo-mdr-381492161417-us-east-1`
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
| Preview image tag updates | `AWS_PROFILE=lif ./release-demo.sh` |
| Apply image tag updates | `AWS_PROFILE=lif ./release-demo.sh --apply` |
| Deploy all stacks | `./aws-deploy.sh -s demo` |
| Deploy one stack | `./aws-deploy.sh -s demo --only-stack <stack-name>` |
| Force ECS redeployment | `./aws-deploy.sh -s demo --update-ecs` |
| Preview MDR frontend deploy | `./release-demo-frontend.sh <git-ref>` |
| Deploy MDR frontend | `./release-demo-frontend.sh <git-ref> --apply` |
| Deploy SAM databases | `./aws-deploy.sh -s demo --update-sam` |
| Deploy MDR database only | `cd sam && bash deploy-sam.sh -s ../demo -d mdr-database` |
| Deploy Dagster database only | `cd sam && bash deploy-sam.sh -s ../demo -d dagster-database` |

## Troubleshooting

### `release-demo.sh` reports ECR access denied
Ensure your AWS session is active and targeting the correct account:
```bash
AWS_PROFILE=lif aws sts get-caller-identity
```

### `release-demo.sh` reports "No image tagged 'latest'"
The dev CI pipeline tags the most recent build as `latest`. If a repository has no `latest` tag, the dev build may not have completed successfully for that service.

### CloudFormation stack stuck in `UPDATE_IN_PROGRESS`
The `cfn-wait.sh` script polls until completion. If a stack is stuck, check the CloudFormation console for event details. Common causes: ECS health check failures, container crash loops, or insufficient permissions.

### MDR frontend build fails
Ensure Node.js 20+ is installed (`node --version`). The build requires `npm ci` to succeed, which needs a valid `package-lock.json` at the specified git ref. If the ref is very old, the frontend directory structure may differ.

### Flyway migration fails
Check the Flyway Lambda logs in CloudWatch (`/aws/lambda/{env}-{user}-flyway`). Common causes: SQL syntax errors in a new migration file, or a migration that conflicts with the current database state.
