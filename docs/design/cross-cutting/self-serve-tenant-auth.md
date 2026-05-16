# Self-Serve Tenant Auth

How a new user, starting from a public landing page, ends up with a workspace they can sign in to, switch between, and invite teammates into — without anyone running an admin script.

## Why this exists

LIF deployments used to require an operator to create accounts and provision database schemas by hand. That was fine for the original demo, but it doesn't scale to "interested parties click around and try LIF themselves." The self-serve track (issues **#882**, **#883**, **#884**) replaces that operator-in-the-loop workflow with three independently deployable layers:

| Layer | Issue | Question it answers |
|---|---|---|
| **Cognito self-serve stack** | #882 | How does a stranger get an account? |
| **Schema-per-tenant** | #883 | Where does their data live, separate from everyone else's? |
| **Workspace selection + invites** | #884 | How do they pick which tenant they're working in, and bring teammates along? |

The layers are loosely coupled on purpose: you can deploy #882 alone (Cognito only, no tenant isolation) or #882+#883 (isolated tenants but no workspace switcher) and the system still works.

## The lifecycle

```
                                          ┌─ MDR /tenants/provision (API-key auth)
                                          │   creates tenant_<sanitized-group> schema
                                          │   via clone_lif_schema() Postgres function
                                          ▼
1. Sign up   ─►  Cognito hosted UI  ─►  post-confirmation Lambda  ─►  MDR
2. Sign in   ─►  Cognito hosted UI  ─►  SPA receives JWT (cognito:groups claim)
3. Use app   ─►  AuthMiddleware reads JWT  ─►  resolves tenant_schema from groups
                                              + workspace selection cookie
4. Invite    ─►  POST /tenants/invite  ─►  signed token  ─►  recipient signs up
                                                              or signs in, then
                                              POST /tenants/invite/accept adds them
                                              to the inviter's Cognito group
```

Each numbered step is described in detail below.

## 1. Sign up — Cognito self-serve stack

**Stack:** A dedicated CloudFormation stack (`cognito-selfserve`), separate from the legacy `EnableCognitoAuth` ALB stubs that predated this work. The legacy stubs aren't used by self-serve; treat any reference to `EnableCognitoAuth` in templates as inherited scaffolding, not a current code path.

**Flow:** Cognito hosts the sign-up UI and sends a confirmation email. The SPA frontend uses Authorization Code with PKCE (no client secret, no implicit grant). On successful confirmation, Cognito triggers a **post-confirmation Lambda**.

**What the Lambda does:** Hits the MDR's `POST /tenants/provision` endpoint (authenticated by a service API key, *not* the new user's JWT — they don't have one yet) with the user's Cognito group name. MDR responds idempotently:

- `201 Created` if the schema was newly minted.
- `200 OK` if the schema already exists (so Lambda retries don't trip Cognito's error handling).
- `400 Bad Request` if the group name sanitizes to an empty schema identifier.

**Why a separate Lambda and not inline in Cognito triggers:** Provisioning a Postgres schema involves a transaction, FK cloning, and sequence reset. Doing that work inside Cognito's 5-second trigger budget is brittle; the Lambda hands off to MDR which can take its time.

## 2. Schema-per-tenant — what `provision_tenant` actually does

**Source of truth:** `clone_lif_schema()` Postgres function, installed via Flyway migration V1.4 (issue #883). MDR's `provision_tenant` Python wrapper sanitizes the Cognito group name into a valid PG identifier (`tenant_lif_team`, `tenant_acme_univ`, etc.) and calls the function.

**What clone_lif_schema does:**

1. Copies all DDL from `public` to `tenant_<group>`.
2. Copies the data (so new tenants start with seed reference data, not empty tables).
3. Re-applies foreign keys pointing to the *new* schema (not back to `public`).
4. Resets sequences so two tenants don't collide on `id` collisions.

**Cutover:** The original `public` schema's content was migrated into `tenant_lif_team` (issue #883 Phase 2 PR 3) so that demo data has a real tenant of its own. After cutover, `tenant_routing__service_schema` configures what API-key callers and group-less Cognito users see — typically `tenant_lif_team`, so service principals route to the same tenant the legacy code used to operate on.

**Tenant routing in the middleware:** Every authenticated request has `request.state.tenant_schema` resolved by `resolve_tenant_schema()` (in `lif/tenant_routing/`). Service principals get the configured service schema; Cognito users get `tenant_<sanitized-first-group>` from their `cognito:groups` claim. The DB session sets `search_path` to that schema before any query runs.

## 3. Sign in & workspace selection — issue #884 Phase 3

After sign-in, the SPA holds a Cognito JWT whose `cognito:groups` claim lists every tenant the user belongs to. The user might belong to one tenant (most cases), or several (after accepting invites).

**Picking a workspace** is the new bit. The frontend asks `GET /tenants/mine` for the list of accessible workspaces, then `POST /tenants/select` to record the user's choice. The selection is stored in a HMAC-signed cookie (`lif_workspace`).

**Why a cookie, not a JWT claim:** Cognito JWTs are issued at sign-in time and can't be partially updated. If the user wanted to switch workspaces during a session, we'd either need to force a re-login or carry the selection out-of-band. A cookie is the cheapest "out-of-band."

**Why this is safe** (a real reviewer asked this): the cookie is only a *selection*, not an authorization. The middleware re-validates on every request that the selected group is actually in the user's current `cognito:groups` claim. A forged or stolen cookie naming a group the user doesn't belong to is silently ignored, falling back to the default. The JWT remains the ground truth for membership; the cookie can only *narrow* what the JWT already proves. See `components/lif/mdr_auth/workspace_cookie.py` for the full security-model docstring.

**SameSite=Lax** is deliberate, not an oversight. `Strict` would drop the cookie on the first request after a cross-site top-level navigation (e.g., clicking an invite-email link), forcing a re-select even though the user already had a valid selection. CSRF on the selection endpoint is mitigated by requiring an `Authorization: Bearer` JWT, which cookies can't supply.

## 4. Invites — issue #884 Phase 3 PR 2

An existing tenant member generates a signed invite token via `POST /tenants/invite`. The token:

- Names the target group + the inviter's Cognito sub.
- Is HMAC-signed (same secret as the workspace cookie) and time-limited (7 days default, see `mdr__invite__token_max_age_seconds`).
- Is **self-contained** — no server-side store of issued tokens. That makes them effectively reusable until expiry, which is fine for v1; single-use enforcement would require a DB table and is deferred.

The recipient registers (or signs in) and presents the token to `POST /tenants/invite/accept`. That endpoint:

1. Verifies the signature and expiry. Bad signature → 400; expired → 410 (Gone).
2. Confirms the token's group still sanitizes to a real schema.
3. Calls Cognito's `AdminAddUserToGroup` to add the recipient.

**Caveat for the frontend:** the recipient's *current* JWT doesn't include the new group; only their next refresh does. The frontend should prompt a token refresh (or full logout/login) before expecting the new workspace to show up in `GET /tenants/mine`.

## Where the code lives

| Concern | Path |
|---|---|
| Cognito stack | `cloudformation/*-cognito-selfserve*.yml` |
| Post-confirmation Lambda | `cloudformation/*-cognito-selfserve*.yml` + Lambda source |
| Schema cloning SQL | `projects/lif_mdr_database/migrations/V1.4__*.sql` |
| `provision_tenant` service | `components/lif/mdr_services/tenant_service.py` |
| Tenant routing | `components/lif/tenant_routing/` |
| Workspace listing & cookie | `bases/lif/mdr_restapi/tenant_endpoints.py`, `components/lif/mdr_auth/workspace_cookie.py` |
| Invite tokens | `components/lif/mdr_auth/invite_token.py`, same endpoints file |
| Auth middleware (resolves all of the above) | `components/lif/mdr_auth/core.py` |

## Status

| PR | Scope | Status |
|---|---|---|
| #883 Phase 1 | clone_lif_schema + provision endpoint | merged |
| #883 Phase 2 | Tenant cutover of demo data | merged |
| #883 Phase 3 | Post-confirmation Lambda wiring | merged |
| #884 Phase 3 PR 1 | `GET /tenants/mine` + `POST /tenants/select` + workspace cookie | in review |
| #884 Phase 3 PR 2 | `POST /tenants/invite` + `POST /tenants/invite/accept` | in review |
| #884 future | Workspace reset, admin endpoints, frontend wiring | not yet split |

For the broader self-serve roadmap and trade-off discussion, see `docs/proposals/mdr-self-serve-registration.md`.
