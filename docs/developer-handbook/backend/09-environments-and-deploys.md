# 9. Environments and deployment (for awareness)

Where merged code goes after `main`, who can deploy it, and why the team's dev and demo run on AWS (not required).

*Checked against main `2967cb9`, November 2026.* Most developers don't have AWS access; this chapter is so you know what happens,
not a runbook.

**AWS is how the team has hosted LIF for demos, not a requirement.** To date (November 2026), the team's
shared dev and demo environments run on AWS: ECS for the services, CloudFormation and SSM for their
configuration, S3 and CloudFront for the MDR UI, Cognito for self-serve sign-up. Apart from the two Cognito-based
features named in [chapter 0](00-start-here.md) (MDR self-serve sign-up, control-plane developer keys), nothing in LIF depends on that choice: the services are containers that need PostgreSQL and MongoDB, which is exactly what
the local stack runs. The AWS scripts and templates in this repo are the team's demo setup, kept as a
reference to adapt ([`docs/operations/guides/deploying-lif-at-your-institution.md`](../../operations/guides/deploying-lif-at-your-institution.md); a hosting-neutral
cloud reference is #1004).

---

## The environments (as of November 2026)

| | Local | dev | demo |
|---|---|---|---|
| Runs on | Docker Compose (`deployments/advisor-demo-docker/`) | AWS ECS (team demo hosting) | AWS ECS (team demo hosting) |
| Image tags | built locally | `:latest` | pinned versions (`:1.2.3`) |
| Organizations | three (org1–org3) | one (`dev-single-org` seed) | three (`advisor-demo-org1/2/3`) |
| Updated by | you | deploy workflows on merge to `main` | manual promotion from dev |

For dev and demo, configuration lives in `{env}.aws` files and `cloudformation/{env}-*.params`, and secrets
are in AWS SSM, wired into each service by `cloudformation/*-taskdef-includes.yml`.

## What happens when your PR merges

- Each service has a workflow in `.github/workflows/` (for example `lif_query_planner_api.yml`) that runs
  on a push to `main` **when its `paths:` match**. It builds the image, pushes it, and updates the team's
  AWS-hosted dev.
- Every deployable project has one such workflow except `lif_control_plane_api` (its workflow is PR #1464)
  and the local-only Dagster projects; [chapter 2](02-codebase-map.md) lists them.
- Changes to a shared brick deploy only through workflows whose `paths:` cover it (#1171; checked by
  `scripts/check_workflow_paths.py`).
- **MDR database migrations are not applied by any of this.** Someone with access applies them by hand:
  [`docs/operations/guides/applying-mdr-migrations.md`](../../operations/guides/applying-mdr-migrations.md).
- **demo** changes only when a maintainer promotes dev's images (`scripts/release-demo.sh`, the
  `promote-to-demo` skill; [`docs/operations/guides/demo-environment-update.md`](../../operations/guides/demo-environment-update.md)).

## If you don't have AWS access

Most contributors don't, and you don't need it to develop LIF.

You can still:

- read every deploy workflow run in the GitHub Actions tab: it shows what was built, from which commit,
  and the build logs (which packages were installed, for example);
- reason about what's deployed from the image tags in the params files.

You can't see ECS task logs, CloudWatch, SSM or the databases. When a change needs any of those, hand it
to a maintainer with access to the team's AWS account (the committers in [`docs/COMMITTERS.md`](../../COMMITTERS.md) can tell you who), and say exactly
what to check.

## Files that reach live environments

These change dev or demo directly rather than through a test, so they're stop-and-ask in
[`agent-behavioral-guidelines.md`](../../../agent-behavioral-guidelines.md):

- `cloudformation/*.params` and the taskdef includes (including the planner's sources config, which in
  the team's AWS-hosted environments comes from SSM through `LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_YAML_SSM`, and the adapters'
  `ADAPTERS__…` credentials in `dagster-ose-taskdef-includes.yml`),
- `.github/workflows/lif_*.yml`,
- the promote-to-demo flow,
- Flyway migrations.

Treat a PR touching them as needing an explicit look from someone who runs the environments.

---

## Where to go next

- [`docs/operations/guides/deployment.md`](../../operations/guides/deployment.md): the scripts, environment differences, ECS debugging.
- [`docs/operations/guides/deploying-lif-at-your-institution.md`](../../operations/guides/deploying-lif-at-your-institution.md): running LIF on your own infrastructure, with or without AWS.
- [Chapter 10](10-extending-lif.md): which parts of LIF run without the full system.
