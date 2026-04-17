# Proposal: MDR Tenant Isolation via PostgreSQL Schema Namespacing + Cognito

**Date:** 2026-02-24
**Status:** Draft — ready for team review
**Related:** `LIF Self-Serve Demo Website Outline.docx`, `plan-demo-user-password.md`

---

## Problem

The LIF demo environment needs to support external evaluators exploring the MDR without interfering with each other or the production demo data. Today there is no registration, no user isolation, and multiple evaluators share the same accounts and data — causing collisions and confusion.

The ambitious design doc (`LIF Self-Serve Demo Website Outline.docx`) estimates 160–260 hours for a full self-serve platform. This proposal scopes a **modest, high-value slice**: Cognito authentication + PostgreSQL schema-based data isolation for the MDR.

---

## Solution Overview

1. **AWS Cognito** replaces the hardcoded user database for MDR authentication
2. **PostgreSQL schema namespacing** gives each guest user their own isolated copy of the MDR data
3. **Role-based schema routing** determines which schema a user operates in
4. The existing `public` schema remains the production demo data used by the translator, GraphQL, and semantic search services

---

## Role-Based Schema Routing

### Roles

| Role | Identity Source | PostgreSQL Schema | Access Level |
|------|----------------|-------------------|--------------|
| **service** | API key (`X-API-Key` header) | `public` | Full — translator, GraphQL, semantic search |
| **admin** | Cognito JWT, `lif-admins` group | `public` (default) | Full — dev team |
| **guest** | Cognito JWT, no admin group | `tenant_{user_id}` | Full — isolated sandbox |

### Routing Logic (in auth middleware)

```
if request has API key → schema = "public"
elif "lif-admins" in JWT cognito:groups → schema = "public"
else → schema = "tenant_{user_id}"
```

### Admin Schema Override (debugging)

Admins can pass an `X-MDR-Schema` header to operate in a guest's schema — useful for debugging issues in a specific user's sandbox. The middleware only honors this header for admin-role users.

```
if admin AND "X-MDR-Schema" header present → schema = header value
```

This means the dev team logs into Cognito like anyone else, but their accounts are in the `lif-admins` group. One auth system for everyone — no separate login flows.

---

## How It Works

### The Key Mechanism: `SET search_path`

PostgreSQL's `search_path` determines which schema is used when queries reference unqualified table names. By setting it per-request, every existing query automatically operates in the right schema with zero changes to service or endpoint code.

```python
# database_setup.py — the single change that propagates everywhere
async def get_session(request: Request) -> AsyncSession:
    async with async_session() as session:
        schema = getattr(request.state, "tenant_schema", "public")
        await session.execute(text(f"SET search_path TO {schema}"))
        yield session
```

All 14 service files and 14 endpoint files are unchanged — they already receive `session` via FastAPI's `Depends(get_session)`. The session just silently operates in the correct schema.

### Schema Provisioning

When a guest registers via Cognito:

1. Cognito post-confirmation Lambda trigger calls `POST /tenants/provision`
2. MDR creates a new PostgreSQL schema: `CREATE SCHEMA tenant_{user_id}`
3. Replays the seed data (DDL + base data model) into the new schema
4. Records the mapping in `public.tenant_schemas` table

### Schema Reset ("Start Over")

Guest clicks "Reset Demo" in the MDR UI:

1. Calls `POST /tenants/reset`
2. MDR drops the schema: `DROP SCHEMA tenant_{user_id} CASCADE`
3. Re-provisions from the seed template

### Schema Cleanup

For abandoned accounts:

- Scheduled Lambda or cron job queries Cognito for inactive users
- Drops their schemas and removes the mapping

---

## What Changes

### Layer 1: Database Session (the lynchpin)

**File:** `components/lif/mdr_utils/database_setup.py`

Modify `get_session()` to accept the `Request` and set `search_path` from `request.state.tenant_schema` before yielding the session.

### Layer 2: Auth Middleware — Tenant Resolution

**File:** `components/lif/mdr_auth/core.py`

Extend `AuthMiddleware.dispatch()`:

1. After authenticating (existing JWT or API key logic), determine the role
2. For API keys: set `request.state.tenant_schema = "public"`
3. For Cognito JWTs: check `cognito:groups` claim
   - If `lif-admins` in groups: set schema to `"public"` (or `X-MDR-Schema` header value if present)
   - Otherwise: look up schema from `public.tenant_schemas` mapping table
4. Replace current custom JWT validation with Cognito JWT validation (RS256 with Cognito JWKS)

### Layer 3: Tenant Service (new component)

**File:** `components/lif/mdr_services/tenant_service.py` (new)

Functions:
- `provision_tenant_schema(session, user_id)` — CREATE SCHEMA + replay seed
- `reset_tenant_schema(session, user_id)` — DROP + re-provision
- `cleanup_tenant_schema(session, user_id)` — DROP + remove mapping
- `resolve_tenant_schema(user_id)` — look up schema name from mapping table

### Layer 4: Tenant Endpoints (new)

**File:** `bases/lif/mdr_restapi/tenant_endpoints.py` (new)

| Route | Method | Purpose | Auth |
|-------|--------|---------|------|
| `POST /tenants/provision` | POST | Provision schema for new user | Cognito Lambda trigger (service key) |
| `POST /tenants/reset` | POST | Reset current user's schema | Guest (self-service) |
| `DELETE /tenants/{user_id}` | DELETE | Drop schema and mapping | Admin only |
| `GET /tenants/status` | GET | Check schema health | Guest (self-service) |
| `GET /tenants/` | GET | List all tenant schemas | Admin only |

### Layer 5: Cognito + CloudFormation

- Cognito User Pool with email verification
- Custom attributes: Organization, Role (optional)
- `lif-admins` group for dev team
- Post-confirmation Lambda trigger → `POST /tenants/provision`
- CloudFormation template for User Pool, App Client, Lambda trigger
- SSM parameters for Cognito Pool ID, App Client ID

### Layer 6: MDR Frontend

- Replace current username/password login with Cognito Hosted UI (or Amplify Auth)
- Pass Cognito JWT in `Authorization: Bearer` header (same pattern, different token issuer)
- Add "Reset Demo" button for guest users
- Show role indicator (admin vs. guest) in UI header

### Layer 7: Seed Script Adaptation

The V1.1 Flyway migration contains DDL + seed data for the `public` schema. We need a version that can be replayed into an arbitrary schema:

- Extract DDL from V1.1 into a parameterized template
- Strip sequence ownership and schema-specific references
- Seed only the base data model (BaseLIF) — guests don't need OrgLIF/PartnerLIF initially

### Layer 8: Sync Connection (`sql_util.py`)

**File:** `components/lif/mdr_utils/sql_util.py`

This uses synchronous `psycopg2` directly (separate from the async ORM). It needs `SET search_path` added after connection, or should receive the schema from the caller.

---

## What Doesn't Change

Because `SET search_path` is transparent to SQLAlchemy:

- **All 14 service files** — unchanged (queries use table names, PostgreSQL resolves to the right schema)
- **All 14 endpoint files** — unchanged (receive session via `Depends`)
- **SQL model definitions** (`mdr_sql_model.py`) — unchanged
- **Schema generation service** — unchanged (operates within session schema)
- **Jinja helper/translation services** — unchanged
- **DataModelType enum and all type-based logic** — unchanged (each schema has its own BaseLIF, OrgLIF, etc.)
- **Frontend API calls** — same endpoints, same request format (just different JWT issuer)

---

## Edge Cases

| Concern | Resolution |
|---------|------------|
| Each schema has its own ID sequences | IDs overlap between tenants — fine, schemas are fully isolated |
| DataModelType.BaseLIF delete protection | Works per-schema — each guest has their own protected BaseLIF |
| `sql_util.py` uses sync psycopg2 | Add `SET search_path` after connect |
| Abandoned guest schemas | Scheduled cleanup job drops schemas for inactive/deleted Cognito users |
| PostgreSQL schema count limits | No hard limit; Aurora handles hundreds of schemas comfortably |
| Cross-schema queries | Not needed — tenants are fully isolated by design |
| Service accounts (translator, GraphQL) | Always route to `public` via API key detection |
| Dev team access to guest data | Admin schema override via `X-MDR-Schema` header |
| Cognito token validation | Replace HS256 custom JWT with RS256 Cognito JWKS verification |
| Existing demo user passwords | Eliminated — Cognito handles all authentication (`plan-demo-user-password.md` becomes moot) |

---

## Effort Estimate

| Area | Hours | Notes |
|------|-------|-------|
| `database_setup.py` — search_path injection | 4–6 | The single change that enables everything |
| `mdr_auth/core.py` — Cognito JWT + role routing | 6–8 | Replace custom JWT with Cognito JWKS validation |
| `tenant_service.py` — provision/reset/cleanup | 8–12 | Schema lifecycle management |
| `tenant_endpoints.py` — new API routes | 4–6 | Thin layer over tenant_service |
| Cognito CloudFormation + Lambda trigger | 8–12 | User Pool, App Client, post-confirmation hook |
| MDR frontend — Cognito auth swap | 6–8 | Replace login form with Cognito Hosted UI |
| Seed script adaptation (V1.1 → parameterized) | 4–6 | Extract DDL + base data into replayable template |
| `sql_util.py` — sync search_path | 2–3 | Small fix for sync connection path |
| Admin schema override (`X-MDR-Schema`) | 2–3 | Header check in middleware, admin-only |
| Testing | 8–10 | Schema isolation, provisioning, role routing |
| **Total** | **52–74 hours** |

With AI-assisted development, this is roughly **2–3 weeks of focused work**.

---

## Migration Path

### Phase 1: Schema isolation (this proposal)
- Cognito + tenant schemas for MDR only
- Dev team as `lif-admins`, guests get sandboxes
- `public` schema unchanged for translator/GraphQL/semantic search

### Phase 2: Advisor integration (future)
- Extend Cognito to Advisor app
- Advisor reads from guest's isolated GraphQL/data stack (separate effort)

### Phase 3: Elevated access (future)
- Guests can request admin access via support workflow
- Move to `lif-admins` group in Cognito

This aligns with the phased approach in the Self-Serve Demo Website Outline while delivering the highest-value piece first.

---

## Open Questions

1. **Seed data scope**: Should guest schemas get only BaseLIF, or also a sample SourceSchema + OrgLIF with mappings so they can experience the full workflow?
2. **Schema naming**: `tenant_{cognito_sub}` works but Cognito subs are UUIDs — long schema names. Alternative: `tenant_{short_hash}`?
3. **Concurrency**: How many simultaneous guest schemas do we expect? 10? 100? This affects Aurora sizing.
4. **Schema TTL**: Auto-expire guest schemas after N days of inactivity? Or keep indefinitely until manual cleanup?
5. **DocumentDB consideration**: If Option C (MongoDB migration from `docs/proposals/migrate-mdr-to-mongodb.md`) is pursued, tenant isolation would use MongoDB databases instead of PostgreSQL schemas. Should we sequence these decisions?
