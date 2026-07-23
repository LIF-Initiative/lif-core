# Proposal: CloudFormation / CI Improvements

Status: Draft (external review)
Date: 2026-07-20
Author: Skills Mobility team (reviewed LIF Core's CF/CI as a starting template for our own AWS setup; sharing back the improvement ideas that surfaced)

## Scope

This is a friendly outside-in review of the AWS delivery setup — `cloudformation/`, `sam/`,
`.github/workflows/`, `.github/actions/`, `aws-deploy.sh`, and the `*.aws` env files. It is
**not** a criticism of the design; the shape is genuinely good and we're adopting large parts
of it. The notes below are the improvements worth considering, roughly in priority order, with
the strengths first so the list stays balanced.

## Strengths worth keeping (don't change these)

- **OIDC role assumption in CI** (`id-token: write` + a GitHub Actions role ARN) — no long-lived
  AWS keys. This is the right pattern.
- **Changeset-based CloudFormation deploys** (`aws-deploy.sh` → `cfn-deploy` with a named
  changeset) — safe, previewable applies.
- **The declarative env file** (`dev.aws` / `demo.aws`: `STACKS` map + `STACK_ORDER` +
  `SAM_STACKS`) — "what deploys, in what order" as one reviewable artifact. Excellent.
- **Composite Actions** (`build-and-push`, `update-cluster`) — DRY build blocks instead of
  copy-pasted steps.
- **Path-filtered triggers** — a service's workflow fires only when that service's files change.
- **One parameterized `service.yml` + a `.params` file per service** — the right reuse unit.
- **docker-compose (local) ↔ CloudFormation (cloud) parity** — same topology both places.

## Recommended improvements

### 1. Add PR-time CI (highest value)

`ARCHITECTURE.md` is candid that "pre-commit hooks are the de facto CI … no automated PR checks
run on feature branches (workflows are deploy-only)." Confirmed: none of the 18 workflows trigger
on `pull_request`. That means the quality gate is a local hook a contributor can skip, and the
first server-side execution of anything is a **deploy from `main`**.

**Suggestion:** add a `pull_request` workflow that runs the gates the repo already values —
`ruff`, `mypy`, `pytest` (and the frontend `build`/`typecheck`) — and mark it a **required status
check** on `main`. This moves correctness left of the deploy and makes a green PR mean something
in CI, not just on the author's machine.

### 2. Build Docker images from the lockfile

`ARCHITECTURE.md` flags that "Docker wheel installs from PyPI, not `uv.lock` … this has caused
production breakage." That's a reproducibility/supply-chain gap: the image can carry different
dependency versions than the ones tested. **Suggestion:** install from the resolved lockfile
(`uv export --frozen` → `requirements.txt`, or `uv sync --frozen` in the build) so the deployed
image matches what CI tested. This likely removes the class of breakage the doc describes.

### 3. Collapse the per-service workflow duplication

There are 18 near-identical per-service workflow files and no `workflow_call`/matrix in use. The
step-level DRY (composite actions) is great; the **workflow-level** duplication is where drift
creeps in (a fix to one has to be copied to 17). **Suggestion:** extract a single reusable
workflow (`on: workflow_call`) parameterized by service/ECR/ECS-service/paths, and have each
service's file be a thin caller — or a matrix over a services list. Fewer files, one place to
change the pipeline.

### 4. Target ECS redeploys to changed services

`aws-deploy.sh --update-ecs` force-new-deployments **every** service in the cluster, not just the
ones whose images changed. Harmless but noisy (and slow as the cluster grows). **Suggestion:**
force-new-deployment only the services affected by the current deploy (the workflows already know
which service they touch via path filters).

### 5. Verify the deploy, don't just trigger it

The deploy workflow ends at "force new deployment"; nothing confirms the new task actually became
healthy. **Suggestion:** add a post-deploy check (wait for the ECS service to reach a steady state
/ hit the service's `/healthz`) so a bad image surfaces in the pipeline instead of silently
running degraded.

### 6. Standardize the Python build tooling

A `setup-poetry` composite action coexists with uv-based service builds (e.g. the orchestrator
workflow installs uv and runs `build.sh`). Mixed toolchains are a small but real maintenance and
"works-on-my-machine" tax. **Suggestion:** pick one (uv, given the direction of travel) and retire
the other from the build path.

### 7. Light secrets-hygiene pass

The committed `.params` files are the right idea, but they're worth an audit to confirm no
sensitive values are inlined — sensitive parameters should use CloudFormation **SSM/Secrets Manager
dynamic references** (`{{resolve:...}}`) rather than literals in a tracked file. (The
`*-workshop-keys.txt` files are correctly untracked — no issue there.)

### 8. Reduce `STACK_ORDER` copy-paste as orgs multiply

`dev.aws`'s org1/org2/org3 blocks are hand-duplicated per tenant. As tenants grow this is
error-prone. **Suggestion:** generate the per-org stack entries from a loop over an org list
rather than maintaining three parallel hand-written blocks.

## Suggested sequencing

1 and 2 are the highest-leverage and independent of the rest — a PR-gate workflow and a
lockfile-based image build. 3–6 are pipeline-quality refinements. 7–8 are cleanups. None require
touching the CloudFormation topology itself.
