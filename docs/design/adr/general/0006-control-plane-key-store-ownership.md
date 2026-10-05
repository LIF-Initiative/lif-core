# ADR 0006: The control plane owns its key store as its own logical database

Date: 2026-10-04

## Status

Proposed

Extends [ADR 0002](0002-lif-control-plane-vs-mdr-host.md) (control plane vs. MDR host). Decides the
spike in #1181, part of epic #1041.

## Context

ADR 0002 moves developer-key issuance out of MDR and into a dedicated control-plane service. It leaves
open where the key store lives once that service exists. #1181 lists three options: the control plane
owns its own database, owns its own schema in the shared MDR cluster, or keeps the table in the MDR
database and connects to it.

ADR 0002 was written against the design in #1033. What shipped in #1038 differs in ways that bear
directly on this choice:

- **Keys are opaque, not signed.** #1033 designed `lifk_<base64url(payload)>.<hmac>`, verifiable
  offline with a shared secret. #1038 shipped `lifk_` plus `secrets.token_urlsafe(32)`, stored as a
  plain SHA-256 hash (`components/lif/mdr_services/developer_api_key_service.py:32-33`). An opaque
  key can only be validated by looking its hash up in the store.
- **Nothing validates keys yet.** LDE's `_developer_key_strategy` is a stub that returns `None`
  (`bases/lif/learner_data_export_api/core.py:31`, `TODO(#1034)`), and deployed LDE runs
  `LDE_AUTH__MODE=composite` (`cloudformation/lif-learner-data-export-api-taskdef-includes.yml:46-47`),
  so in practice it accepts Cognito JWTs only. Nothing reads `KeyHash` or writes `LastUsedDate`.
- **The table is cloned into every tenant schema.** V1.5 creates `public."DeveloperApiKeys"` and
  copies it into each existing `tenant_*` schema
  (`sam/mdr-database/flyway/flyway-files/flyway/sql/mdr/V1.5__developer_api_keys.sql`). Rows carry
  no workspace column. A key's workspace is whichever schema the request's `search_path` selected
  (`components/lif/mdr_utils/database_setup.py:147`).
- **MDR's tenant lifecycle reaches the keys.** `reset_tenant` runs `DROP SCHEMA … CASCADE` and then
  re-clones (`components/lif/mdr_services/tenant_service.py:103-104`), which deletes that workspace's
  keys. `clone_lif_schema` copies data as well as DDL by default (`include_data boolean DEFAULT true`,
  `V1.4__clone_lif_schema_overriding_identity.sql:45`), so any key rows in `public` would be copied
  into every new tenant.
- **MDR connects as the cluster's master user.** The MDR stack sets `DBUsername: postgres`
  (`sam/mdr-database/template.yaml:89`), and `mdr-api` reads that user from SSM. There are no
  per-schema or per-service roles. A separate schema in MDR's database would separate the tables but
  not the access.
- **Each Aurora cluster has exactly one database.** `aurora-postgres.yml:385` sets one `DatabaseName`
  per cluster, and nothing under `sam/` runs `CREATE DATABASE`. Dagster already has its own cluster,
  built from a near-copy of the MDR stack (`sam/README.md`). Flyway manages only `public`, and
  migrations run only when `deploy-sam.sh` deploys a new image tag
  (`docs/operations/guides/applying-mdr-migrations.md`).

Two constraints from the rest of the epic also apply. #1189 must show the control plane issuing,
validating and revoking keys "with no MDR running anywhere". #1183 must migrate the live dev and demo
keys without a destructive cutover.

## Decision

1. **The control plane owns its key store as its own logical Postgres database.** It has its own
   connection settings, its own database login, and its own Flyway migration set and history. It
   never shares MDR's database, MDR's login or MDR's migrations, and MDR never reads the store.
2. **Where that database runs is a deployment choice.** In dev and demo it may be a second database
   on the existing MDR Aurora cluster, which avoids a third cluster. A deployer may point it at any
   Postgres, including a dedicated cluster or a local container. The service only knows a connection
   string.
3. **One table, scoped by an explicit workspace column.** The control-plane store holds every key in
   a single table. Each row records the workspace it belongs to, instead of relying on per-tenant
   copies and `search_path`. `KeyHash` should be unique, because any validator of an opaque key looks
   it up by hash. Column names and types are settled in #1180 and #1183.
4. **Existing keys are copied, not moved.** The migration copies rows out of each
   `tenant_*."DeveloperApiKeys"` table into the new store, tagged with the workspace they came from.
   Hashes carry over unchanged because they are plain SHA-256. Rows get new `Id`s, since today's
   `Id`s are per-schema identities and collide across tenants. The MDR tables stay in place and
   untouched until the cutover in #1185 retires MDR's key endpoints. Dropping them is a separate,
   later step.
5. **This ADR does not decide the key format.** Whether keys stay opaque, with validation by lookup
   against the store or a control-plane verify endpoint, or become the signed tokens ADR 0002
   describes, is #1184's decision. The storage choice above works for either.

## Alternatives

- **The control plane owns its own Aurora cluster (strict option 1).** Not required. It gives the
  strongest isolation, but it adds a third cluster per environment, a cost that a separate logical
  database avoids in dev and demo. A deployer who wants it can still choose it under decision 2.
- **Its own schema in the MDR database (option 2).** Rejected. MDR connects as the master user, so
  a separate schema gives no access isolation. The control plane would also depend on MDR's database
  being up, which leaves #1189's "no MDR anywhere" only half true.
- **Keep the table in the MDR database (option 3).** Rejected. It recreates the coupling ADR 0002
  exists to remove. It also keeps both tenant-lifecycle hazards: a workspace reset deletes that
  workspace's keys, and the clone copies data into new tenants.
- **Keep per-workspace tables in the control-plane store.** Rejected. Per-schema tables only made
  sense because MDR routes by `search_path`. A validator of an opaque key would have to search every
  schema for a hash, and every migration would have to loop over the schemas, as V1.5 does.

## Consequences

- The control plane can run without MDR, which #1189 requires, and MDR's tenant reset can no longer
  delete keys.
- **The premises of ADR 0002 were not implemented as written.** The key logic is not in a portable
  `developer_keys` brick (noted on #1041, 2026-08-31), and the keys are not signed. Extraction is
  therefore a rewrite of storage and tenancy as well as a re-deploy. This ADR records that rather
  than editing ADR 0002.
- **Dev and demo need a database-provisioning step that does not exist today.** Adding a second
  database to the MDR cluster needs a `CREATE DATABASE` and a login, plus a Flyway runner for the
  new migration set. This is AWS work, owned by #1182.
- **The copy migration needs read access to every `tenant_*` schema** in the MDR database, so it
  runs once, with MDR's credentials, outside the control plane's normal access. Between the copy and
  the cutover, keys created in MDR do not reach the new store, so #1183 and #1185 have to be
  sequenced to avoid a gap, for example with a final re-copy just before the cutover.
- **Until #1184 lands, keys still authenticate nothing.** That lowers the risk of the migration, but
  it also means `LastUsedDate` stays empty, so the usage and audit views in #1186 and #1188 have no
  data to show.
- **Decisions 1–4 don't depend on the database engine; only the Flyway migration set is
  Postgres-specific.** If LIF's storage later moves to a document store such as MongoDB, the store
  stays the control plane's own database with one workspace-scoped collection. The unique `KeyHash`
  index would then have to be created by the control plane itself, not by an image entrypoint
  (compare `person_identifier_idx`, #1307).

### Effect on the follow-on issues in #1041

| Issue | Change |
|---|---|
| #1180 | Extract the key logic into a `developer_keys` brick as planned. The brick's model should not assume `search_path` scoping. The workspace column can be added here or in #1183. |
| #1182 | Includes provisioning the control-plane database (a second database on the MDR cluster in dev/demo), its login, and a Flyway runner for its migration set. |
| #1183 | The non-destructive copy from per-tenant tables into the single workspace-scoped table, with new `Id`s and a final re-copy before cutover. |
| #1184 | Decides opaque-with-lookup vs. signed keys. ADR 0002's signed format was never built. |
| #1185 | Retires MDR's key endpoints and keeps MDR's tables until a separate drop step. |
| #1186, #1188 | Depend on #1184 writing `LastUsedDate` and revocation data. |
| #1189 | The control plane plus LDE needs only a Postgres connection string, not MDR. |

## References

- #1181 (this spike), epic #1041, sub-issues #1180 and #1182–#1189
- [ADR 0002](0002-lif-control-plane-vs-mdr-host.md); [ADR 0001](auth.md)
- #1000 (LDE auth spike), #1033 (designed key format), PR #1038 (shipped store), #1034 (validation stub)
- #1290 (deployable MDR without AWS), #1316 / PR #1323 (non-AWS test-drive)
- [`docs/design/cross-cutting/self-serve-tenant-auth.md`](../../cross-cutting/self-serve-tenant-auth.md)
- [`docs/operations/guides/applying-mdr-migrations.md`](../../../operations/guides/applying-mdr-migrations.md)
