# Self-Serve (#884) Demo Promotion Cheatsheet

Tactical runbook for promoting the #884 self-registration story from dev → demo. Built on findings from the dev debugging session on 2026-05-26 (one day before the 2026-05-27 client demo).

**Use alongside, not instead of, [`demo-environment-update.md`](demo-environment-update.md).** That guide is the canonical end-to-end. This one focuses only on the #884-specific deltas that we discovered the hard way on dev.

## TL;DR — execution order

```bash
# 1. Pre-flight SSM params (creates post-confirm key on both sides)
AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo
AWS_PROFILE=lif ./scripts/setup-mdr-api-keys.sh demo --apply

# 2. Promote demo image tags (standard process)
AWS_PROFILE=lif ./scripts/release-demo.sh
AWS_PROFILE=lif ./scripts/release-demo.sh --apply

# 3. Deploy demo-lif-mdr-api (new task def picks up POST_CONFIRM + Cognito + tenant routing env vars)
./aws-deploy.sh -s demo --only-stack demo-lif-mdr-api

# 4. Deploy demo-lif-mdr-cognito (adds lif-team group + replaces post-confirmation Lambda code)
./aws-deploy.sh -s demo --only-stack demo-lif-mdr-cognito

# 4b. Deploy SAM mdr-database (Flyway migrations V1.2/V1.3/V1.4)
#     CRITICAL: without this, the new post-confirm Lambda's /tenants/provision
#     call 500s because the `clone_lif_schema` PG function (V1.2) doesn't
#     exist. Discovered during the 2026-05-27 demo promotion.
#     BUILDX_NO_DEFAULT_ATTESTATIONS=1 is required on Apple Silicon — otherwise
#     Docker emits an OCI multi-arch image index that Lambda's image pull
#     can't follow.
cd sam && BUILDX_NO_DEFAULT_ATTESTATIONS=1 AWS_PROFILE=lif \
  bash deploy-sam.sh -s ../demo -d mdr-database
cd ..

# 5. Deploy MDR frontend (covers PR #935 redirect fix as well)
AWS_PROFILE=lif ./scripts/release-demo-frontend.sh main --apply

# 6. Clean out stale test users (their eval-* groups exist but their tenant schemas don't)
#    — see "Stale user cleanup" below

# 7. Add the demo account to lif-team if you want it pre-staged
AWS_PROFILE=lif aws cognito-idp admin-add-user-to-group \
  --user-pool-id $(aws cloudformation describe-stacks --stack-name demo-lif-mdr-cognito \
      --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text) \
  --username <demo-account-email> \
  --group-name lif-team
```

## Why this is more than a normal demo update

The standard `demo-environment-update.md` flow promotes the latest image tags. For #884, **the CloudFormation templates also drifted from prod** over the 6 weeks between when the work landed and when we're shipping it. The templates carry:

- A new `LifTeamGroup` resource in `cognito-selfserve.yml`
- A new post-confirmation Lambda body that calls MDR's `POST /tenants/provision`
- New env vars + secret refs in `lif-mdr-api-taskdef-includes.yml` and `service.yml` (`POST_CONFIRM` key, `COGNITO_USER_POOL_ID`, `COGNITO_SPA_CLIENT_ID`, `COGNITO_REGION`, `TENANT_ROUTING__ENABLED`, `TENANT_ROUTING__SERVICE_SCHEMA`)

Image-only promotion (step 2 alone) **will not** ship the schema-per-tenant or invite features. Steps 3-4 are required.

## Required application-code fixes that must be in the image you promote

The promotion only ships fixes that have already merged into `main` and made it into the MDR API image. Two of those landed late in dev debug and you'll want to verify they're in the `lif_mdr_api:latest` image you're promoting:

| PR | What it fixes | How to spot the unfixed-version symptom |
|---|---|---|
| **[#949](https://github.com/LIF-Initiative/lif-core/pull/949)** | Tenant search_path missing `public` → PG enum types (`elementtype`, `datamodelelementtype`) fail to resolve | `GET /datamodels/with_details/<id>` returns 500 for `OrgLIF` models (e.g. StateU LIF #17, Org2 LIF #18); browser console misreports it as a CORS error. Fix: `SET search_path TO "<tenant>", public` in `components/lif/mdr_utils/database_setup.py`. |
| **[#940](https://github.com/LIF-Initiative/lif-core/pull/940)** + **[#939](https://github.com/LIF-Initiative/lif-core/pull/939)** | V1.3 migration ran the buggy V1.2 `clone_lif_schema`; `flyway repair` now runs before `migrate` | The Flyway Lambda fails on first deploy with `cannot insert a non-DEFAULT value into column "Id"` — see Step 4b below. |

Verify before deploy:
```bash
# Confirm the image tag in demo's params has both fixes (these PRs merged 2026-05-26+)
grep -E "ImageUrl|ImageTag" cloudformation/demo-lif-mdr-api.params
# Pull the image's commit SHA from its tag and check `git log` to confirm
# the merge commits for #949 + #940 are reachable.
```

If demo's `ImageUrl` is `…/lif_mdr_api:latest` (rare for demo — it usually pins a timestamped tag), step 2 below picks up whatever the latest dev build is. If pinned, make sure the pinned tag was built AFTER 2026-05-26 (when #949 + #940 merged).

## Findings worth keeping in mind

| # | Finding | Demo-day implication |
|---|---|---|
| 1 | Post-confirmation Lambda is the **only** thing that provisions a new tenant's PG schema. If the old Lambda body is deployed (no MDR call), users get Cognito groups but no schemas. | After step 4, do a fresh self-serve registration end-to-end before the demo. If the new tenant's `/explore` works, you're good. |
| 2 | Cognito group name `lif-team` (Precedence: 10) → routes to `tenant_lif_team` schema (precedence beats auto-created `eval-<sub>` groups, so the LIF data wins in the JWT's group ordering). | The demo path "I can switch to the original LIF data" relies on this. Verify the group exists in demo after step 4. |
| 3 | `lif_workspace` cookie is HttpOnly + `SameSite=Lax`; frontend must use `withCredentials: true` (shipped on `main`); backend CORS must `allow_credentials=true` (already wired in `dev-lif-mdr-api.params`, mirror in `demo-lif-mdr-api.params`). | Pre-flight check: `grep CORS demo-lif-mdr-api.params`. Must allow the demo frontend origin. |
| 4 | After joining a new group via invite or admin-add, the user's existing JWT does **not** reflect it. They must log out + back in. | Tell the demo audience this *before* they click. Otherwise the new workspace card just doesn't appear. |
| 5 | The `EnableCognitoAuth=false` param is **legacy** (it controlled the old ALB-Cognito stub). Self-serve Cognito runs independently of this flag. Don't get tempted to flip it. | n/a — just don't touch it. |
| 6 | MDR API logs `DATABASE_URL` with the credential in plaintext to CloudWatch at startup (`lif.mdr_utils.database_setup`). **Pre-existing, not from #884.** | Out of scope for the demo; capture as a post-demo follow-up. Sensitive in shared log groups. |
| 7 | **`clone_lif_schema` copies tables but NOT PG `CREATE TYPE` definitions.** Tenant-scoped queries that cast against an enum (e.g. `'Entity'::elementtype`) fail because the type lookup uses search_path, which previously didn't include `public`. PR [#949](https://github.com/LIF-Initiative/lif-core/pull/949) appends `public` to the search_path as a fallback so types resolve correctly. | Without #949 in the deployed image: opening any `OrgLIF` data model (StateU LIF, Org2 LIF, future per-org models) returns 500 from `/datamodels/with_details/<id>`, surfaced in the UI as "Network Error" + a misleading CORS error in console. Fixed dev on 2026-05-26 evening; must be in demo image too. Permanent fix is to extend `clone_lif_schema` to copy types, then drop the fallback. |

## Stale user cleanup

If anyone has tested registration on demo before steps 3-4 deployed (or before today), their Cognito group exists but their PG schema doesn't. Two paths:

**Path A (clean — drop + re-register):**
```bash
USER_POOL_ID=$(AWS_PROFILE=lif aws cloudformation describe-stacks \
  --stack-name demo-lif-mdr-cognito \
  --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text)

# For each test user:
AWS_PROFILE=lif aws cognito-idp admin-delete-user --user-pool-id "$USER_POOL_ID" --username <email>

# Find the orphan eval-* group (named after their sub):
AWS_PROFILE=lif aws cognito-idp list-groups --user-pool-id "$USER_POOL_ID" --query 'Groups[?starts_with(GroupName,`eval-`)].GroupName'
AWS_PROFILE=lif aws cognito-idp delete-group --user-pool-id "$USER_POOL_ID" --group-name <eval-…>

# They re-register fresh; new Lambda fires; PG schema gets created
```

**Path B (retroactive — manually provision the existing user's schema):**

Call MDR's `POST /tenants/provision` with the `mdr-post-confirm` API key:
```bash
API_KEY=$(AWS_PROFILE=lif aws ssm get-parameter \
  --name /demo/mdr-post-confirm/MdrApiKey --with-decryption \
  --query 'Parameter.Value' --output text)

curl -X POST "https://mdr-api.demo.lif.unicon.net/tenants/provision" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"group": "eval-<the-users-sub>"}'
```

Path A is cleaner for the demo because it exercises the full live flow.

## Smoke tests before the demo

After all steps complete, verify in this order:

1. **MDR API health** — `curl https://mdr-api.demo.lif.unicon.net/health-check` returns 200
2. **Cognito group exists** — `aws cognito-idp list-groups | grep lif-team` shows it with Precedence 10
3. **Fresh registration works** — register a test email; confirm; should land on `/workspaces` showing one card; click it; `/explore` shows seed data (the new tenant has just-cloned `public` data — not the LIF team data, but it should *load*)
4. **lif-team join works** — add the test user to lif-team via CLI; sign out + back in; `/workspaces` now shows two cards; clicking lif-team enters real LIF data
5. **Invite flow works** — generate invite link from lif-team workspace; open in another browser profile / incognito; register a second test user; click the invite URL; should succeed, prompt re-login; second user sees lif-team in their list

## Rollback plan

If a step fails or the demo blows up on stage:

- **Step 3 (mdr-api) rolls back** automatically via CloudFormation if the task fails to start. The old task def revision is preserved.
- **Step 4 (cognito) rolls back** the same way. The `lif-team` group would be deleted; existing users' `eval-*` groups stay. UserPool itself is `Replace: False`, so user accounts and existing memberships are safe.
- **Frontend rollback** — re-run `release-demo-frontend.sh <previous-git-ref> --apply`.
- **Database rollback** — n/a. The schema-per-tenant cutover happened in #883 Phase 2 PR 3 (already on demo); we're not changing schemas in this promotion.

## Related links

- [Self-serve auth design doc](../../design/cross-cutting/self-serve-tenant-auth.md)
- [Demo environment update guide](demo-environment-update.md) — full update process
- [Self-serve registration walkthrough](self-serve-registration-walkthrough.md) — tester flow
- PRs: #914 (workspace listing), #918 (invites), #931 (reset), #932 (export), #934 (UI), #935 (redirect fix)
