# MDR Tenant Isolation — Q&A from Design Review

**Date:** 2026-02-24
**Context:** Questions raised during team design review of `mdr-tenant-isolation-cognito.md`

---

## Team Questions

### 1. Does Alex (AWS Ops) need to be involved? If so, in what way/effort?

**Yes, but scoped to two areas:**

| Area | Alex's Role | Effort |
|------|------------|--------|
| Cognito CloudFormation | Author or review the User Pool, App Client, and Lambda trigger templates. This is IAM/infrastructure work that fits his lane. | 4–8 hours |
| Aurora capacity review | Confirm the dev/demo Aurora instance can handle the expected schema count. May need to adjust instance class or storage. | 1–2 hours |

Everything else (database_setup.py, auth middleware, tenant service, frontend) is application code that the dev team handles. Alex doesn't need to touch the MDR codebase — just the CloudFormation templates and a quick Aurora sanity check.

**Timing:** He can work the Cognito stack in parallel with the application changes. No blocking dependency until integration testing.

---

### 2. Eight layers change — what is the risk to the stability of our existing code?

The 8 layers are misleading — most are **new files**, not modifications to existing code.

| Layer | Change Type | Risk | Why |
|-------|------------|------|-----|
| 1. `database_setup.py` | **Modify** | **Medium** | The single riskiest change — if `search_path` isn't set correctly, queries hit the wrong schema. But it's ~5 lines of code, and the fallback is `public` (current behavior). |
| 2. `mdr_auth/core.py` | **Modify** | **Medium** | Replacing JWT validation with Cognito JWKS. Risk is breaking existing auth. Mitigated by keeping API key auth untouched (services keep working). |
| 3. `tenant_service.py` | **New file** | **Low** | Additive — no existing code changes. |
| 4. `tenant_endpoints.py` | **New file** | **Low** | Additive — new routes, no existing routes affected. |
| 5. Cognito CloudFormation | **New stack** | **Low** | Separate infrastructure — doesn't touch existing stacks. |
| 6. MDR frontend auth | **Modify** | **Medium** | Swapping login mechanism. Risk is locking out users during transition. |
| 7. Seed script | **New file** | **Low** | Additive — V1.1 migration stays untouched. |
| 8. `sql_util.py` | **Modify** | **Low** | Small change, and this code path is rarely used. |

**Bottom line:** Only 3 existing files are modified (`database_setup.py`, `mdr_auth/core.py`, `sql_util.py`). The 14 service files and 14 endpoint files are completely untouched. The blast radius is narrow.

---

### 3. Can we do a small-scale POC first to build confidence?

**Absolutely — strongly recommended.** Here's a POC that proves the core mechanism in a day or two:

**POC Scope: Schema Isolation Only (No Cognito)**

1. Manually create a second schema in the dev MDR database:
   ```sql
   CREATE SCHEMA poc_tenant_1;
   SET search_path TO poc_tenant_1;
   -- Replay V1.1 DDL + minimal seed data
   ```

2. Add `search_path` injection to `database_setup.py` with a header-based toggle:
   ```python
   schema = request.headers.get("X-MDR-Schema", "public")
   await session.execute(text(f"SET search_path TO {schema}"))
   ```

3. Test with curl/Postman:
   - `GET /datamodels/` with no header → returns `public` schema data (existing demo)
   - `GET /datamodels/` with `X-MDR-Schema: poc_tenant_1` → returns tenant data
   - `POST` to create an entity in `poc_tenant_1` → verify it doesn't appear in `public`
   - Verify translator/GraphQL still work (they don't send the header → `public`)

4. Verify zero bleed-through (see question below for full test plan)

**POC Effort: 4–6 hours.** No Cognito, no frontend changes, no CloudFormation. Just proves the core `search_path` mechanism works end-to-end through the existing MDR API.

---

## Additional Design Considerations

### Could we scope a schema to a Cognito group instead of per-user?

**Yes — and there's clear value.** Instead of 1 user = 1 schema, a Cognito group maps to a shared schema. Use cases:

- A team from the same organization evaluating together
- A workshop cohort sharing a dataset
- The dev team already benefits from this (`lif-admins` group → `public`)

The mapping table becomes `(cognito_group, schema_name)` instead of `(user_id, schema_name)`. The middleware checks group membership first, falls back to per-user schema. Minimal extra effort — maybe 2–3 hours on top of the base estimate.

### Layer 7 — should we ensure data portability (import/export) first?

**Agreed this is the right sequencing.** The MDR already has `/import_export/export/{data_model_id}` and `/import_export/import/` endpoints. If we ensure those work reliably for a full round-trip (export base model → import into fresh schema), then:

1. Provisioning uses the import endpoint rather than raw SQL replay
2. V1.1 seed data can eventually be stripped to just DDL (no COPY statements)
3. Base data becomes a JSON fixture file rather than embedded SQL

Recommendation: **POC uses raw SQL replay, production uses import/export** — validates both paths.

### Auto-expiry — how do we warn users?

Suggested UX:

- **On login:** Banner: "Your demo environment expires on {date}. Export your work to keep it."
- **7 days before expiry:** Email via Cognito + SES (Cognito can trigger Lambda on custom events)
- **On expiry:** Schema is archived (renamed to `expired_{user_id}_{date}`) for 30 days, then dropped
- **Post-expiry login:** "Your environment has expired. Reset to start fresh or contact support."

This is Phase 2 polish — not needed for POC or MVP.

---

## Technical Risk Questions

### What is the blast radius if `search_path` misbehaves?

**Contained.**

- **Worst case (wrong schema):** A user sees another tenant's data. Detectable in POC testing. Mitigated by validating the schema name against the mapping table before setting it.
- **Worst case (SET fails):** SQLAlchemy raises an exception, the request returns 500. No data corruption — it's a session-level setting, not a DDL change.
- **Service accounts are immune** — API key auth always routes to `public` before the search_path logic runs.
- **Rollback:** Remove the one `SET search_path` line → everything uses `public` again.

### How do we prove zero schema bleed-through?

**POC test plan:**

1. Create entity "CANARY_TENANT_1" in `poc_tenant_1`
2. Create entity "CANARY_PUBLIC" in `public`
3. Query `public` — must see CANARY_PUBLIC, must NOT see CANARY_TENANT_1
4. Query `poc_tenant_1` — must see CANARY_TENANT_1, must NOT see CANARY_PUBLIC
5. Run the full integration test suite against `public` — must pass unchanged
6. Automate as a recurring integration test for CI

### What is the rollback plan?

1. **Code rollback:** Revert `database_setup.py` (remove `SET search_path`) and `mdr_auth/core.py` (revert to custom JWT). Two-file revert, everything works as before.
2. **Data rollback:** Tenant schemas are isolated — `DROP SCHEMA tenant_xxx CASCADE` cleans up completely. `public` schema is never modified by tenant operations.
3. **Cognito rollback:** Cognito User Pool is a separate CloudFormation stack. Delete it. Re-enable the hardcoded user database in `core.py`.

### What happens if provisioning partially fails?

Schema creation is a two-step process: `CREATE SCHEMA` then seed. If seeding fails:

- The schema exists but is empty/incomplete
- Tenant status endpoint returns "unhealthy"
- Resolution: `DROP SCHEMA ... CASCADE` and retry
- Can wrap in a transaction: if seed fails, schema creation rolls back

Design the provisioning to be **idempotent** — calling it twice for the same user either succeeds (already provisioned) or retries cleanly.

### How many schemas can Aurora handle under expected load?

PostgreSQL has **no hard limit** on schemas. Aurora PostgreSQL inherits this. Practical considerations:

| Scenario | Tables | Storage | Impact |
|----------|--------|---------|--------|
| 10 tenants | ~150 tables | ~20 MB | Trivial |
| 100 tenants | ~1,500 tables | ~200 MB | Comfortable |
| 1,000 tenants | ~15,000 tables | ~2 GB | Monitor `pg_catalog` query times |

Each tenant's seed data is ~2MB (V1.1 is 1.9MB). For the expected load (10–50 evaluators), Aurora won't even notice.

### Does this conflict with the MongoDB migration proposal?

**No conflict for sequencing.** If we build this now on PostgreSQL and later pursue the MongoDB migration (`migrate-mdr-to-mongodb.md`):

- `SET search_path` maps to **MongoDB databases** (each tenant gets their own DB, connection switches per-request)
- Middleware logic (role → schema routing) translates directly
- Cognito integration is database-agnostic — stays the same
- Tenant service interface stays the same, just the implementation changes

Building on PostgreSQL now is not wasted work — the patterns carry over.

### Can we spike schema isolation before Cognito?

**Yes — that's exactly what the POC is.** Use the `X-MDR-Schema` header as the tenant selector. No Cognito needed. Proves the hardest part (database isolation) independently from the auth plumbing.

**Recommended build sequence:**

1. **POC** (1–2 days): Schema isolation with header-based switching
2. **Cognito setup** (parallel, Alex): User Pool, groups, Lambda trigger
3. **Integration** (~1 week): Wire Cognito JWT → middleware → search_path
4. **Frontend** (~1 week): Swap login, add reset button
