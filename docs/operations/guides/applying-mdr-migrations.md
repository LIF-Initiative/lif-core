How to apply an MDR Flyway migration to dev or demo, and how to confirm it actually landed.

# Applying MDR database migrations

**Merging a migration to `main` does not apply it.** No service deploy applies it either. Someone has to run the procedure below, and until they do, the repo's schema and the database's schema differ with nothing reporting it.

That gap is tracked in [#1226](https://github.com/LIF-Initiative/lif-core/issues/1226). It has bitten us once already: in [#1123](https://github.com/LIF-Initiative/lif-core/issues/1123) the `V1.5` migration sat merged while API-key creation returned 500 on both environments.

## TL;DR

From the **repo root**, with Docker running and an active `lif` AWS session:

```bash
aws sso login --profile lif && export AWS_PROFILE=lif

bash sam/deploy-sam.sh -s dev  -d sam/mdr-database   # dev
bash sam/deploy-sam.sh -s demo -d sam/mdr-database   # demo
```

Then [verify it applied](#verifying-it-applied) — do not assume.

## Why a merge isn't enough

The migrations are baked into a container image, and the run is triggered by a **parameter change**, not by a merge:

1. `sam/mdr-database/flyway/Dockerfile` does `COPY flyway-files /`, so every `V1.*.sql` is *inside* the image.
2. `FlywayLambdaFn` (`${env}-mdr-flyway`) runs that image with `FLYWAY_LOCATIONS: filesystem:/flyway/sql/mdr`.
3. `FlywayLambdaFnTrigger` is a `Custom::FlywayTrigger` whose properties include **`pImageTag`**. CloudFormation re-invokes a custom resource only when its properties change.

So Flyway runs when — and only when — a **new image tag** is deployed to the `mdr-database` SAM stack.

None of the `.github/workflows/lif_*.yml` service workflows build that image or touch that stack; they deploy service containers. A migration file added in a PR changes nothing until `deploy-sam.sh` rebuilds the image with a fresh `DATE_TAG` and deploys it.

> `sam/mdr-database/flyway/README.md` says *"Flyway runs automatically during deployments."* That is true of **SAM deployments of this stack** and false of every other kind of deployment. It is the sentence most likely to mislead you.

## What the script does

`sam/deploy-sam.sh -s <env> -d sam/mdr-database`:

| step | effect |
|---|---|
| sources `<env>.aws` | sets `SAM_CONFIG_ENV`, `AWS_REGION` |
| `buildDockerImages` | builds `sam/mdr-database/flyway/`, pushes `${env}-mdr-flyway:latest` **and** `:$DATE_TAG` to ECR |
| `samBuild` | `sam build` |
| `samDeploy` | `sam deploy --config-env <env> --parameter-overrides "… pImageTag=$DATE_TAG"` |
| CloudFormation | sees `pImageTag` changed → re-invokes `Custom::FlywayTrigger` → `${env}-mdr-flyway-invoker` → `${env}-mdr-flyway` → `flyway migrate` |

`DATE_TAG` is `$(date +%F_%H-%M-%S)`, so every run produces a new tag and therefore always re-triggers.

## Prerequisites

- **Docker running.** The script builds an image; it fails at `buildDockerImages` otherwise.
- `aws`, `sam`, `yq`, `docker` on `PATH` (the script checks and dies with a clear message).
- An active SSO session: `aws sso login --profile lif`, then `export AWS_PROFILE=lif`. Run it in the **foreground** — the browser callback has to land while the command is alive.

## Environments

| env | `-s` | SAM stack | flyway function |
|---|---|---|---|
| dev | `dev` | `dev-lif-sam-resources` | `dev-mdr-flyway` |
| demo | `demo` | `demo-lif-mdr-db-resources` | `demo-mdr-flyway` |

Apply to **dev first**, verify, then demo.

## Verifying it applied

The deploy reporting success is not sufficient evidence — check the database side.

**When did Flyway last run?**

```bash
aws logs describe-log-streams --log-group-name /aws/lambda/dev-mdr-flyway \
  --order-by LastEventTime --descending \
  --query 'logStreams[0].lastEventTimestamp' --output json
```

Convert the epoch milliseconds and confirm it is *now*, not a previous run. A stale timestamp means the trigger did not fire — usually because `pImageTag` did not change.

**What tag is deployed?**

```bash
aws cloudformation describe-stacks --stack-name dev-lif-sam-resources \
  --query 'Stacks[0].Parameters[?ParameterKey==`pImageTag`].ParameterValue' --output text
```

**What did the run do?** Read the newest `/aws/lambda/dev-mdr-flyway` log stream — Flyway prints each migration it applies and the resulting schema version.

## Local docker-compose is different — and weaker

Locally, `V1.*.sql` files are replayed through `psql` with **no Flyway history table**. Every file runs on every start, in file order.

Two consequences:

- **V1.2+ migrations must be idempotent** (`CREATE OR REPLACE`, `ADD COLUMN IF NOT EXISTS`, existence-guarded constraints). A non-idempotent migration works under real Flyway and breaks locally on the second start.
- **A local pass proves very little about a real environment.** It does not exercise Flyway's version tracking, ordering against already-applied state, or the trigger path above.

`V1.6__attributes_target_entity_id.sql` is a good reference for the idempotent style.

## Troubleshooting

**Deploy succeeded but Flyway did not run.** Check `pImageTag` actually changed. CloudFormation skips custom-resource re-invocation when properties are identical.

**Deploy fails at `buildDockerImages`.** Docker is not running, or `aws ecr get-login-password` lacks credentials — confirm `aws sts get-caller-identity` works first.

**A column is missing at runtime but the migration is in the repo.** That is this document's entire subject: the migration has not been applied. Check the last-run timestamp above before debugging the application.

**The SQLModel declares a column the database lacks.** Any `select(<Model>)` names every mapped column, so Postgres errors on the whole query rather than just that field. Apply the migration; there is no application-side workaround.

## Related

- [#1226](https://github.com/LIF-Initiative/lif-core/issues/1226) — no gate reports repo-vs-database migration drift
- [#1123](https://github.com/LIF-Initiative/lif-core/issues/1123) — the outage caused by an unapplied V1.5
- [#1225](https://github.com/LIF-Initiative/lif-core/issues/1225) — schema duplicated across `backup.sql` and `V1.1`
- `CLAUDE.md` § MDR Schema Migrations — the idempotency rule
