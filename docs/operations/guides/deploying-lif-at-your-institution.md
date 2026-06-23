# Deploying LIF at Your Institution

> **Audience:** A technical team at an adopting institution (university, system office, EdTech provider) that wants to run its **own** LIF instance — not contribute to LIF Core, and not operate the LIF Initiative's hosted demo. If you only want to *try* LIF locally, stop here and run the [local demo](../../../deployments/advisor-demo-docker/README.md) instead.
>
> **Status:** This guide is the adopter-facing **hub**. Most steps link to existing in-depth guides (the "spokes"). Sections marked **🚧 Gap** are not yet fully documented for the self-host case; each links to its tracking issue. Tracked by #1004.

LIF is **infrastructure, not a turnkey product** — a set of composable microservices for aggregating learner data from your source systems (SIS, LMS, HR) into a standardized record. Deploying it means standing up those services, defining your data model in MDR, and wiring your sources in. This guide gives you the end-to-end path and points to the detailed runbook for each step.

For the service catalog and how the pieces fit, read [`docs/overview/services-overview.md`](../../overview/services-overview.md) first if you haven't.

---

## Prerequisites

Before you start, you should have:

- **Docker** 20.10+ and **Docker Compose** v2 (for the local/single-node path). See the [demo prerequisites](../../../deployments/advisor-demo-docker/README.md#pre-requisites).
- **A target environment.** Decide early — see [Step 1](#step-1-choose-your-deployment-shape). The cloud path additionally needs an AWS account, the AWS CLI/SAM CLI, and familiarity with CloudFormation.
- **Your source systems identified.** Know which systems (SIS, LMS, HR, credential issuers) you'll pull from, how each is accessed (REST, auth scheme), and the shape of the data each returns. You'll need this in [Step 5](#step-5-connect-your-data-sources).
- **A data-model plan.** Know which LIF entities/attributes you need and what (if anything) you must extend or constrain. Background: [`docs/overview/mdr-overview.md`](../../overview/mdr-overview.md) and [`docs/lif-data-model-distinctions.md`](../../lif-data-model-distinctions.md).
- **An LLM API key** *(only if you deploy the AI Advisor)* — e.g. `OPENAI_API_KEY`.

You do **not** need a deep Polylith or Python background to deploy — that's for contributors. See [`CONTRIBUTING.md`](../../../CONTRIBUTING.md) only if you intend to modify service code.

---

## Step 1: Choose your deployment shape

LIF scales from a laptop to a multi-tenant cloud deployment. Pick the smallest shape that meets your goal and graduate later.

| Shape | Use it for | What you get | Start from |
|---|---|---|---|
| **Local eval** | Demos, evaluation, a single analyst exploring | Full stack on one machine via Docker Compose, with seeded sample data | [`deployments/advisor-demo-docker/`](../../../deployments/advisor-demo-docker/README.md) |
| **Single-node, your data** | A pilot with real (non-prod) institutional data, one org | Same compose stack, your data model + your sources, no sample data | This guide, Steps 2–6 |
| **Cloud / multi-org** | Production, multiple tenants, external access, self-serve onboarding | AWS-hosted services, schema-per-tenant isolation, Cognito auth | [Step 3](#step-3-stand-up-the-stack) + 🚧 Gap below |

> **🚧 Gap — portable cloud topology.** The only cloud deployment documented today is the LIF Initiative's **own** AWS environment (`dev`/`demo`), described in [`deployment.md`](deployment.md). Those scripts and CloudFormation templates assume LIF-Initiative AWS accounts, SSO, and ECR registries — they are a **reference to adapt, not a drop-in**. A portable, adopter-neutral cloud reference (Terraform/CDK or generalized CloudFormation, sizing guidance) is not yet written. Track / +1: **#1004**.

For relative scope of work items as you plan, see [`docs/operations/t-shirt-sizing.md`](../t-shirt-sizing.md).

---

## Step 2: Get the code

```bash
git clone git@github.com:LIF-Initiative/lif-core.git
cd lif-core
```

Adopters are expected to **fork** and keep their environment-specific deployment under `deployments/<your-org>/` so it stays isolated from upstream changes. See [`deployments/README.md` → For Adopters](../../../deployments/README.md#for-adopters). Start by copying `deployments/advisor-demo-docker/` as your template.

---

## Step 3: Stand up the stack

### Local / single-node (Docker Compose)

The shipped reference target brings up the whole stack — MDR (+ Postgres), GraphQL APIs, Query Planner/Cache, Translator, Identity Mapper, Orchestrator (Dagster), Semantic Search, and the Advisor UI/API.

```bash
cd deployments/<your-org>      # your copy of advisor-demo-docker
export OPENAI_API_KEY=...       # only if running the Advisor
docker compose up --build -d
```

Verify the core endpoints respond (adjust ports to your compose file):

| Service | Default URL |
|---|---|
| MDR UI | http://localhost:5173/ |
| MDR API | http://localhost:8012/health-check |
| GraphQL (org1) | http://localhost:8010/graphql |
| Advisor UI | http://localhost:5174/ |

Tear down with `docker compose down -v` (the `-v` also drops seeded volumes).

> **Note on MDR migrations in compose:** local compose replays every `V1.*.sql` through `psql` without Flyway history tracking, so migrations must be idempotent. This and other build/runtime gotchas are documented in [`deployment.md` → MDR Schema Migrations](deployment.md#mdr-schema-migrations-v12). Read that section before customizing the database.

### Cloud / multi-org

See the **🚧 Gap** note in [Step 1](#step-1-choose-your-deployment-shape). Until a portable reference exists, use [`deployment.md`](deployment.md) and [`demo-environment-update.md`](demo-environment-update.md) as the worked example of a cloud deployment and adapt the `{env}.aws` config, CloudFormation params, and `aws-deploy.sh` to your own accounts.

---

## Step 4: Define your data model in MDR

LIF services load their schema **from MDR at startup** — so your data model is configuration, not code. In the MDR UI you will:

1. Start from **Base LIF** (the canonical shared model) and create your **Org LIF** model, including the Base LIF fields you need.
2. **Extend** with institution-specific attributes and **constrain** which fields are exposed, plus define custom value sets — all at runtime, no code changes.

- Concepts and how schema flows: [`docs/overview/mdr-overview.md`](../../overview/mdr-overview.md)
- What LIF's model does that others don't (and the deployer's responsibilities): [`docs/lif-data-model-distinctions.md`](../../lif-data-model-distinctions.md)
- Naming/structure rules you must follow (PascalCase entities vs. camelCase scalars, reserved words): [`docs/specs/data-model-rules.md`](../../specs/data-model-rules.md)

---

## Step 5: Connect your data sources

Each upstream system is wired in through an **adapter** (how LIF fetches/authenticates) plus **source schema + JSONata mappings** (how its data becomes LIF-shaped), all configured via MDR and the Orchestrator.

- End-to-end tutorial (a custom REST source with bearer auth): [`add-data-source.md`](add-data-source.md)
- The adapter contract — what an adapter receives and returns, when to write a new one: [`creating-a-data-source-adapter.md`](creating-a-data-source-adapter.md)

Two reference adapter flows ship in the repo (`LIF-to-LIF` and `Example Data Source to LIF`); start from whichever is closest to your source.

---

## Step 6: Auth, tenancy, and API keys

Match the auth posture to your deployment shape:

- **Local dev:** auth is **disabled by default** (`GRAPHQL_AUTH__API_KEYS` empty). Fine for evaluation only.
- **Service-to-service / workshop API keys** for the GraphQL API: [`graphql-api-keys.md`](graphql-api-keys.md) (SSM-backed key storage, the `X-API-Key` flow, `setup-graphql-api-keys.sh`).
- **Multi-tenant self-serve onboarding** (Cognito sign-up → schema-per-tenant → workspace selection → invites): the design narrative is [`self-serve-tenant-auth.md`](../../design/cross-cutting/self-serve-tenant-auth.md); the operator/tester walkthrough is [`self-serve-registration-walkthrough.md`](self-serve-registration-walkthrough.md).

> **🚧 Gap — adopter auth model.** The self-serve stack (#882/#883/#884) is documented against the LIF Initiative's Cognito setup. Standing it up under *your* identity provider / AWS account is not yet written as an adopter recipe. Until then, treat the self-serve docs as a reference architecture. Track: **#1004**.

---

## Step 7: Operate and upgrade

Day-2 operations. Several of these are currently documented only for the LIF-internal environment — adapt as needed.

- **Upgrades & breaking changes:** always read [`MIGRATION.md`](../../../MIGRATION.md) and [`CHANGELOG.md`](../../../CHANGELOG.md) before pulling a new version.
- **Schema migrations:** [`deployment.md` → MDR Schema Migrations](deployment.md#mdr-schema-migrations-v12) and `sam/README.md` for the Flyway-based path.
- **Load/perf expectations:** [`load-testing.md`](load-testing.md).
- **🚧 Gap — backups, monitoring, and DB recovery** for a self-hosted instance are not yet documented (`operations/guides/README.md` lists a `mdr-database-recovery.md` that does not exist yet). Track: **#1004**.

---

## Where to go when you're stuck

- **Service responsibilities & flows:** [`docs/overview/services-overview.md`](../../overview/services-overview.md)
- **Architecture & the polylith layer model:** [`ARCHITECTURE.md`](../../../ARCHITECTURE.md)
- **Full doc index:** [`docs/INDEX.md`](../../INDEX.md)
- **Community discussion:** GitHub Discussions (see the root [`README.md`](../../../README.md#community-support)).

---

*Last verified: 2026-06-22 against the `advisor-demo-docker` local stack. The cloud and operations spokes are partially documented — see the 🚧 Gap notes. Re-verify against a real adopter deployment when one exists.*
