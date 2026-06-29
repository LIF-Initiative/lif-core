---
name: promote-to-demo
description: Promote the current dev build to the demo environment — bump image tags from dev :latest, deploy the ECS stacks, the MDR frontend, and (if migrations changed) the SAM databases. Gates the promotion on explicit user sign-off after a dev check.
argument-hint: [all|stacks|frontend|sam]
allowed-tools: Bash, Read, Agent
---

Promote dev → demo via the safe path. Demo runs **pinned** image tags; dev runs `:latest`. Promotion = copy the current dev tags into `cloudformation/demo-*.params`, deploy the stacks, redeploy the MDR frontend, and migrate the SAM databases only if Flyway SQL changed. This is the executable form of [`docs/operations/guides/demo-environment-update.md`](../../../docs/operations/guides/demo-environment-update.md) — that guide is the source of truth.

**The hard gate:** demo is the stakeholder-facing environment. Do **not** promote until the change has been validated on dev (`*.dev.lif.unicon.net`) — a check by you or the user, not just "it deployed." Stop and get explicit sign-off before Phase 2.

## Arguments

- `all` (default) — image-tag bump → stacks → frontend → SAM-if-needed.
- `stacks` — just the image-tag bump + ECS stack deploy.
- `frontend` — just the MDR frontend (S3 + CloudFront).
- `sam` — just the SAM databases (when Flyway migrations changed).

All commands run from the **repo root** with `AWS_PROFILE=lif` and an active SSO session. Prerequisites: AWS CLI v2, `jq`, `yq`, `docker`, Node 20+, SAM CLI.

## Pre-flight (always)

1. **Confirm dev is validated.** Ask the user to confirm the change works on dev. If they haven't checked, stop — offer to run the `verify` skill against dev first. Per the gate above, an automated smoke is **not** a substitute for a human touching the feature on dev.
2. **SSO session live:** `AWS_PROFILE=lif aws sts get-caller-identity` — if it errors, tell the user to run `! aws sso login --profile lif`.
3. **One deploy at a time.** Never run multiple `aws-deploy.sh` invocations in parallel — concurrent runs cause SSO login conflicts (CLAUDE.md).
4. **SSM parameters exist?** First-ever promotion of a service needs its SSM params (MDR/GraphQL API keys) created or ECS tasks fail to launch. Check the guide's Step 0; surface to the user if a new service is in this batch.

## Phase 1 — Bump image tags (dry-run first)

```bash
AWS_PROFILE=lif ./scripts/release-demo.sh            # dry-run: shows which demo-*.params change and to what tags
```
Show the user the proposed tag changes. On approval:
```bash
AWS_PROFILE=lif ./scripts/release-demo.sh --apply
git diff cloudformation/demo-*.params                # each ImageUrl should now be a timestamped tag, not :latest
```
Review the diff with the user before deploying.

## Phase 2 — GATE, then deploy stacks  *(scope: all | stacks)*

**STOP. Confirm sign-off to promote to demo.** Then:
```bash
./aws-deploy.sh -s demo                              # deploys all stacks in STACK_ORDER (~34 stacks)
```
- One service only: `./aws-deploy.sh -s demo --only-stack demo-lif-<service>`
- Force restart when the task-def didn't change but you need fresh containers: `./aws-deploy.sh -s demo --update-ecs`

ECS rolls each service to the new image. Watch for failed tasks (see CLAUDE.md § Debugging ECS Services — the dev/demo log group + `describe-services` events).

## Phase 3 — MDR frontend  *(scope: all | frontend)*

The MDR frontend is static (S3 + CloudFront), **not** ECS — deployed separately from a git ref:
```bash
AWS_PROFILE=lif ./scripts/release-demo-frontend.sh main           # dry-run: shows SHA, bucket, API URL
AWS_PROFILE=lif ./scripts/release-demo-frontend.sh main --apply   # worktree build + sync + CloudFront invalidation
```
Any ref works (`main`, a tag, a SHA). The script builds in a temp worktree with `VITE_API_URL` pointed at the demo MDR API and cleans up after itself.

## Phase 4 — SAM databases, only if Flyway SQL changed  *(scope: all | sam)*

Skip unless `sam/*/flyway/` has new/changed SQL. Confirm with the user whether migrations changed.
```bash
./aws-deploy.sh -s demo --update-sam                 # mdr-database + dagster-database
```
- One DB: `cd sam && bash deploy-sam.sh -s ../demo -d mdr-database`
- **`V1.1` was *replaced* (not a new V1.2)?** Flyway won't re-run it — the DB must be reset (**destroys MDR data**): `AWS_PROFILE=lif ./scripts/reset-mdr-database.sh demo --apply` (dry-run without `--apply`). Confirm with the user first.

## Phase 5 — Verify & record

```bash
AWS_PROFILE=lif ./scripts/verify-demo-images.sh      # param-file tags vs running ECS tasks
```
- Spot-check demo health endpoints / the relevant surface (or run the `verify` skill against demo).
- **Commit the pinned tags** so the promotion is tracked:
  ```bash
  git add cloudformation/demo-*.params
  git commit -m "Issue #XXX: Update demo image tags to match dev"
  ```
  Open a PR per the repo convention.

## Rules

- **No promotion without dev validation + explicit sign-off.** The dev round-trip is the hard gate.
- **Deploy sequentially** — never parallel `aws-deploy.sh`.
- **Always dry-run** `release-demo.sh` / `release-demo-frontend.sh` / `reset-mdr-database.sh` and show the diff before `--apply`.
- **SAM/DB reset destroys data** — confirm explicitly; never run `reset-mdr-database.sh --apply` unprompted.
- If any step fails, **stop and report** — don't continue down the phase list on a red step.
