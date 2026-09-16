# Identity Mapper

Version 1.0.0

**Table of Contents**

[Overview](#overview)

[Motivation](#motivation)

[Design Proposal](#design-proposal)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Key Concept](#key-concept)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Functional Requirements](#functional-requirements)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Interaction with Other LIF Components](#interaction-with-other-lif-components)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Design Assumptions](#design-assumptions)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Design Requirements](#design-requirements)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Performance](#performance)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Concurrency](#concurrency)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[High Level Design](#high-level-design)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Identity Mapper Storage](#identity-mapper-storage)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Identity Mapper Service](#identity-mapper-service)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Dependencies](#dependencies)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Exceptions and Errors](#exceptions-and-errors)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Data validation exception](#data-validation-exception)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Mapping exception](#_Toc198241137)

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;[Example Usage](#example-usage)

[Liveness and Startup Validation](#liveness-and-startup-validation)

[Performance Report](#performance-report)

[Possible Future Roadmap Items](#possible-future-roadmap-items)

# Overview

The **Identity Mapper** facilitates the resolution of person identifiers from external partner organizations to the internal identifiers utilized within the organization. This component enables cross-organizational sharing of LIF records for individuals using the respective identifiers from each organization.

# Motivation

When an external organization requests a LIF record for a person via the LIF API, the identifier used in the request may belong to that organization's proprietary system. To accurately retrieve data for the person, external identifiers must be mapped to the internal identifiers maintained by the organization.

The **Identity Mapper** component addresses this need by resolving person identifiers from an external organization to the corresponding internal identifiers. It maintains the relationship between a person's identifiers across the two organizations, enabling the Query Planner to resolve the internal identifier needed to query data from internal systems and the cache.

# Design Proposal

## Key Concept

The **Identity Mapper** is a standalone component that maps person identifiers of two organizations. The **Identity Mapper** is intended to be populated by an internal system having knowledge of the relationship between identifiers used by two organizations. It is invoked by the **Query Planner** when there is a need to translate an external person identifier into an internal identifier.

![](media/image_identityMapper_4.png)

*Image 1: A simple diagram depicting how the Identity Mapper functions at a high-level*

## Functional Requirements

This component has the following specific requirements:

1.  Ability to store mappings of person identifiers between two
    organizations, each identified by a unique identifier

2.  Ability to perform CRUD operations on the identity mapping database
    via an API

3.  Ability to populate identity mapping database through a bulk upload
    process (Possible Future Roadmap Item)

## Interaction with Other LIF Components

This component primarily interacts with the **Query Planner**, which invokes it to retrieve the internal identifier for a person based on the identifier provided in the **LIF API** request by an external organization.

## Design Assumptions

1.  The LIF Framework does not assume or require the creation of a universal person identifier to map person identities across organizations or systems.

2.  The **Identity Mapper** component is not intended to serve as an identity mastering service; its purpose is limited to resolving external identifiers to internal ones for data requested via the **LIF API**.

3.  The organization maintains a unique primary identifier for each person.

4.  This component is limited to mapping person identifiers and will not store any other attribute. Any use case requiring the resolution of person attributes, such as mapping a name to an identifier, must be handled upstream in the processing flow.

5.  A user interface is not required to view or manage the mapping of person identifiers.

6.  Organizations in the LIF ecosystem are uniquely identified though identifiers such as DUNS number.

## Design Requirements

### Performance

(Possible Future Roadmap Item) The component should provide consistent performance irrespective of the volume of the requests and number of identity mapping records.

### Concurrency

Concurrent endpoint requests are addressed through parallel threads implemented with reliability considerations.

## High Level Design

The **Identity Mapper** is a standalone component that enables the conversion of a person identifier from an external organization to an internal identifier. As depicted below, the proposed design envisions Identity Mapper storage, along with an Identity Mapper service that provides CRUD operation endpoints.

![](media/image_identityMapper_5.png)

*Image 2: Simple diagram depicting the relationship between the ID Mapper Service and ID Mapper Storage*

The **Identity Mapper** is called by the **Query Planner** after determining external information is needed to satisfy a data request (after checking the **Query Cache** for internal information).

### Identity Mapper Storage

The design proposes using a relational or key-value data store for storage, along with the implementation of an **Identifiers Map** table with the following attributes to store the relationship between person identifiers from two organizations.

-   **Mapping ID:** An identifier generated automatically to uniquely identify relations between identifiers

-   **LIF Organization ID:** Unique identifier of organization hosting LIF

-   **LIF Organization Person Identifier:** Identifier used by the LIF hosting organization to identify a person

-   **External Organization ID:** Unique identifier of external organization

-   **External Organization Person Identifier:** Identifier used by the external organization to identify a person

A uniqueness constraint should be enforced on the combination of LIF Organization ID, LIF Organization Person Identifier, External Organization ID, and External Organization Person Identifier.

### Identity Mapper Service

The following methods should be implemented in the Identity Mapper Service to save, retrieve, and delete mappings:

1.  **Save Mappings:** POST organizations/{org_id}/persons/{person_id}/mappings

2.  **List Mappings:** GET organizations/{org_id}/persons/{person_id}/mappings

3.  **Delete Mappings:** DELETE organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}

Delete refusals are deliberately indistinguishable. `DELETE` answers **404** both when no mapping has
that ID and when the mapping exists but belongs to a different organization or person. Answering the
second case with a distinct 400 let a caller probe arbitrary IDs and learn which ones were real
without being able to read or delete them ([#1177](https://github.com/LIF-Initiative/lif-core/issues/1177)).
The storage layer still reports `NOT_FOUND` and `NOT_OWNED` separately and the service logs a warning
naming the organization and person on `NOT_OWNED`, so a cross-organization attempt stays visible to an
operator even though it is invisible to the caller.

The diagrams in the following section illustrate the internal steps the service should implement to enable the above methods.

1.  **Save Mappings:** A collection of mappings should be passed to the method for saving the mappings in the storage.

![](media/image_identityMapper_3.png)

*Image 3: Workflow diagram for the Save Mappings method*

2.  **List Mappings:** The workflow below illustrates the steps the service should implement to list the mappings for a given organization and person.

![](media/image_identityMapper_2.png)

*Image 4: Workflow diagram for the List Mappings method*

3.  **Delete Mappings:** The workflow below illustrates the steps the service should implement to delete the mapping for a given organization and person.

![](media/image_identityMapper_1.png)

*Image 5: Workflow diagram for the Delete Mappings method*

## Design Requirements

### Performance

(Possible Future Roadmap Item) The component should provide consistent performance irrespective of the volume of the requests and number of identity mapping records.

### Concurrency

Concurrent endpoint requests are addressed through parallel threads implemented with reliability considerations.

## Dependencies

None

## Exceptions and Errors

### Data validation exception

This exception occurs when uniqueness constrains for External and Internal Identity Map are about to be violated during data insertion.

## Example Usage

TBD

## Possible Future Roadmap Items

- [Issue #12: Add Identity Mapper Support for Bulk Upload Process](https://github.com/LIF-Initiative/lif-core/issues/12)

# Liveness and Startup Validation

`GET /health` reports liveness against the real datastore: it runs `SELECT 1` through the session
factory and returns **200** when the database is reachable and **503** when it is not. The query
runs off the event loop via `asyncio.to_thread`, matching the mapping handlers, so a hung database
cannot stall unrelated requests.

**Startup behavior is a deliberate decision (see Issue #1215).** The service starts even when the
database is unreachable and lets `/health` report unhealthy so the orchestrator / load balancer can
restart the task; the lifespan does not fail on a down database. This matches the sibling services
and avoids blocking a rollout on a transient DB blip. The pre-#1178 connection check is not a
precedent worth restoring — it existed only as a side effect of a leftover debug log, never as a
decision.

Three places declare the check, and they are **not** interchangeable:

- **`cloudformation/lif-identity-mapper-taskdef-includes.yml`** declares a container-definition
  `HealthCheck`. This is the one that matters on ECS. Fargate does *not* monitor a `HEALTHCHECK`
  baked into the image — only a `healthCheck` in the container definition — so without this block
  "steady state" means merely that the container did not exit, which is exactly how #1215's silent
  `SUCCEEDED` happened.
- **`Dockerfile` and `Dockerfile2`** declare an image `HEALTHCHECK` polling the same route. This
  covers `docker compose` and plain `docker run`, where the image instruction *is* honoured.
- **`HealthCheckUrl` in the six `{dev,demo}-lif-identity-mapper-org{1,2,3}.params`** files points at
  `/health`. This is currently **inert**: `cloudformation/service.yml` reads it only inside the
  target group, which is created under `Condition: UseLbForService`, and that is `false` for this
  service. It is set correctly so the value is right if a load balancer is ever enabled here.

With the task-definition block in place, a deploy against an unreachable database fails its health
check, never reaches steady state, and the rollout fails instead of reporting `SUCCEEDED`.

# Performance Report

Issue [#13](https://github.com/LIF-Initiative/lif-core/issues/13) investigated and improved the
Identity Mapper against the *Performance* and *Concurrency* design requirements above (sub-issue of
the performance epic #1131; sibling of the #10 composer work). Validation run 2026-08-16 against the
standalone mariadb container with a local uvicorn server.

## Findings (code review)

| # | Problem | Location |
|---|---|---|
| P0 | Blocking sync SQLAlchemy inside `async def` handlers on the single FastAPI event loop; uvicorn runs 1 worker → concurrent requests serialize on DB latency | all `IdentityMapperSqlStorage` methods |
| P0 | `save_mappings` N+1: per-mapping session/transaction, ~2-3 round trips + 1 commit each (~250 for a 100-mapping batch); partial saves on mid-batch failure | service + SQL storage |
| P1 | `delete_mapping` = 4 SELECTs + 1 DELETE across 3 sessions | service + storage + CRUD |
| P1 | `session.refresh()` after `flush` on create/update → extra SELECT per row; all columns are client-assigned | CRUD |
| P2 | Model declares 5 single-column indexes that production DDL does not have → 5 unused indexes under auto-create | model |
| P2 | Leftover `DEBUG: …SELECT 1…` log at startup; engine pool not env-configurable | db |

## Changes

1. `save_mappings` is now **all-or-nothing**: one session, one transaction, one batched read, a
   per-row no-op/update/insert (duplicate keys within a batch keep last-wins upsert semantics), and a
   single commit; any failure rolls everything back and raises a `DataStoreException`.
2. Every storage method offloads DB work off the event loop via `asyncio.to_thread(...)`.
3. `delete_mapping` collapses 4 SELECTs + 1 DELETE across 3 sessions into 1 SELECT + 1 DELETE in 1
   session. Ownership is checked **inside that transaction**, between the SELECT and the DELETE, and
   the storage call reports `DELETED` / `NOT_FOUND` / `NOT_OWNED` so the service kept its 404-vs-400
   responses (the 400 was later folded into the 404 by #1177; the enum still separates the two for logging). Validating ownership from the return value *after* the transaction committed was the
   defect in #1150: the delete was already durable, so the error raised afterwards could not undo it.
4. Dropped `session.refresh()` (one fewer SELECT per create/update) and the 5 unused indexes.
5. Engine now configurable via `IDENTITY_MAPPER_DB_POOL_SIZE` (default 10) and
   `IDENTITY_MAPPER_DB_POOL_PRE_PING` (**default true**). Pre-ping defaults on because this change
   removed the startup `SELECT 1` — the only connection validation — while raising the pool from 5
   to 10 and letting more connections idle on threads; without it, connections outlive MariaDB's
   `wait_timeout` and surface as intermittent "server has gone away" 500s. Both are wired into
   `cloudformation/lif-identity-mapper-taskdef-includes.yml`.
6. A client-supplied `mapping_id` must name a row the caller already owns, and must agree with the
   `target_system_id` / `target_system_person_id_type` sent alongside it. Either violation raises
   `ValueError` → **400**. Previously an unrecognized id fell through to the create branch, copied
   itself into a new row's primary key and failed the unique constraint as an opaque 500 — which,
   once the batch became all-or-nothing, discarded every other mapping in the request.
7. `save_mappings` returns one entry per persisted row. A batch carrying the same key twice yields
   one entry, not two entries pointing at the same row.

## Validation

Wall-clock bench, re-run 2026-09-01 with `development/scripts/bench_lif_identity_mapper.py` against
the `lif-identity-mapper-db` container (MariaDB 10.11, production DDL) and a local uvicorn. Both code
states were measured back to back on the same machine in the same sitting, so the ratios are
comparable; "before" is the pre-#13 tree at `c3dce0e`. Medians: n=1 and n=10 over 25 runs, n=100 and
n=500 over 5. Every run uses a fresh org/person.

**POST save** (ms):

| n | before | after | Δ |
|---|---|---|---|
| 1 | 14.2 | 16.8 | 0.85× — *slower*, see below |
| 10 | 222.6 | 42.0 | ~5.3× |
| 100 | 2275.5 | 84.6 | ~26.9× |
| 500 | 12801.1 | 159.1 | **~80×** |

**GET** (ms):

| n | before | after |
|---|---|---|
| 1 | 6.4 | 7.0 |
| 10 | 7.3 | 8.1 |
| 100 | 16.7 | 16.6 |
| 500 | 43.4 | 28.9 |

**DELETE**, one HTTP request per mapping (ms):

| n | before | after | Δ |
|---|---|---|---|
| 1 | 21.4 | 17.8 | |
| 10 | 295.2 | 216.1 | ~1.4× |
| 100 | 2827.6 | 2119.8 | ~1.3× |
| 500 | 16558.7 | 10739.6 | ~1.5× |

- **POST save** is the headline: the old per-mapping-transaction path is superlinear
  (222→2275→12801 ms), the batched path near-flat (42→85→159 ms). The earlier ad-hoc run recorded
  ~14.7× at n=500; that was measured while each insert still flushed individually. With the flush
  batched it is ~80×.
- **n=1 is marginally slower** (14.2 → 16.8 ms, ~2.6 ms). The batch path reads the person's existing
  mappings before deciding create-vs-update and hops through `asyncio.to_thread`, neither of which
  the old single-mapping save did. The cost is fixed and small, and it buys atomicity and the curve
  above; worth knowing rather than hiding.
- `pool_pre_ping` was checked separately and its cost is inside run-to-run noise at this scale
  (n=1 POST 16.8 ms with it on, and a 24.5 ms median in a noisier 5-run sample with it off).
- **Statement counts** for a 500-mapping batch, from `before_cursor_execute` events:

  | code state | SELECT | INSERT |
  |---|---|---|
  | this branch as first benched (flush per row) | 1 | 500 |
  | this branch now (single flush) | 1 | 1 |

  SQLAlchemy's `insertmanyvalues` collapses the staged inserts into one statement, so the batch
  costs 2 statements rather than 501. `test_save_mappings_issues_one_insert_for_the_whole_batch`
  guards it and fails with `assert 50 == 1` against the per-row-flush implementation.
- **DELETE** cuts per-request DB queries from 5 to 2; the wall-clock win stays modest because one
  mapping is deleted per HTTP request and the round trip dominates.
- **GET** was already one indexed SELECT; unchanged except at n=500.
- Absolute figures differ substantially from the 2026-08-16 run (which recorded a 1669 ms before at
  n=500 against this run's 12801 ms) — different hardware, container state and method. That
  divergence is the reason the harness is now committed rather than left ad hoc.
- Live correctness on the mariadb container: batch create assigns IDs; re-POST of an existing key
  upserts and preserves the original `mapping_id`; duplicate keys in one batch collapse to a single
  row with last-wins value and a single response entry; DELETE returns 204; DELETE of a missing ID
  returns 404.

### Concurrency (50 parallel GETs)

| mode | wall (ms) | p50 (ms) | p95 (ms) |
|---|---|---|---|
| before (blocking event loop) | 51.0 | 21.7 | 38.1 |
| after (`asyncio.to_thread`)  | 66.7 | 36.0 | 55.4 |

Wall time is equivalent between the two approaches. Root cause: `pymysql` is pure-Python, so the DB
work is **GIL-bound** — the event loop was never the throughput ceiling. The value of `to_thread` is
therefore **event-loop non-starvation** (the *Concurrency* requirement): DB latency no longer blocks
the single event loop, so slow or latent DB queries (or mixed async work such as the query planner's
HTTP calls) no longer stall unrelated requests. True single-host throughput needs a follow-up:
async SQLAlchemy with a C-extension async MariaDB driver (`asyncmy`/`aiomysql`), matching the MDR
brick's async pattern.

### Table-size sweep (record-count half, issue #1219)

The batch-size tables above hold the table at near-zero rows, so they answer the *volume of the
requests* half of the Performance requirement but never exercised the *number of identity mapping
records* half. The harness was extended in #1219 to seed the table and re-time each operation at a
fixed batch size (n=100) as the table grows. Run 2026-09-13 against the same
`lif-identity-mapper-db` container (MariaDB 10.11, production DDL) and a local uvicorn. Medians of 5
runs.

Seeding method (re-runnable): the harness POSTs the rows through the same API it benches, 500 rows
per request, one fresh `seed-org-*` / `seed-person-*` pair per request spread across 10 org ids.
Targets are **cumulative** — the table is grown to each target and benched, never reset — so a
re-run must start from a known table (recreate the container or truncate). Seeding cost: 10k rows in
20 requests (~1s), 100k in 180 (~9s), 1M in 1800 (~824s).

| operation | rows=0 | rows=10,000 | rows=100,000 | rows=1,000,000 |
|---|---|---|---|---|
| POST save | 13.0 | 15.5 | 33.5 | 1064.2 |
| GET | 4.0 | 5.7 | 24.3 | 1129.1 |
| DELETE (per-row) | 385.6 | 357.6 | 371.5 | 509.4 |

Flat through 100k rows, then a hard knee at 1M. The curve is not a workload artifact — the benched
rows are fresh (org, person) pairs, so POST/GET hold their cost to the index descent and DELETE is
a PK lookup; table size is the only variable. The knee is the schema. `SHOW INDEX` reports
`uq_identity_mapping` as **`HASH`**, and `EXPLAIN` at 1M shows `type=ALL, key=NULL` (rows≈934k): the
mappings lookup is a **sequential scan**, never the composite unique key. The four key columns
(`VARCHAR 255/255/255/100`, utf8mb4) total 865 chars / 3460 bytes, over InnoDB's 3072-byte B-tree
key limit; MariaDB 10.11 degrades the oversized key to an unusable HASH index instead of erroring
(MySQL 8 rejects the same DDL with "Specified key was too long"). Reproduced on the container: the
same DDL with 240-byte key columns is created as `BTREE`; at the original width it is `HASH`. The
batch-size tables above therefore cannot show this: at near-zero row counts a sequential scan fits in
cache and looks every bit like the "one indexed SELECT" the code review assumed.

**Verdict.** The *number of identity mapping records* half of the requirement was **not met at 1M
rows under the schema as measured** — POST and GET degrade ~25 ms → ~1.1 s. The reads are point
queries and the workload is fine; `uq_identity_mapping` just is not a usable index. The read path
is fixed in [#1231](https://github.com/LIF-Initiative/lif-core/issues/1231); the unique key itself
is still `HASH`, tracked in [#1258](https://github.com/LIF-Initiative/lif-core/issues/1258). See
below.

### Resolution (#1231) — the read path

`read_by_lif_org_and_person` — the GET handler and the save pre-read, and the only
table-size-sensitive read — now has a dedicated B-tree of its own:

```sql
INDEX idx_org_person (lif_organization_id, lif_organization_person_id)
```

Measured on a clean `mariadb:10.11` at 50,000 rows after `ANALYZE TABLE`, against the production
DDL:

| DDL | `EXPLAIN` (2-column lookup) | per-lookup |
|---|---|---|
| before | `type=ALL`, `key=NULL`, rows=49758 | 15.3 ms |
| after | `type=ref`, `key=idx_org_person`, rows=5 | ~0.05 ms |

Two things worth carrying forward:

- **The penalty was never only at 1M.** The index was unusable at *every* table size; what grows
  with row count is just what the full scan costs. At 10k–100k the scan hides inside HTTP overhead,
  which is why the curve above reads as flat-then-knee.
- **`uq_identity_mapping` is still `HASH`, deliberately.** Narrowing the key columns to
  `VARCHAR(191)` would have made it a real B-tree (verified: 2692 bytes, `BTREE`, `type=ref`) and
  would additionally make the DDL portable to MySQL 8, which rejects it outright today. That was
  weighed against the additive index and not taken here, because it changes a column-width contract
  for no measured read gain — the two fixes time identically. The constraint still enforces
  uniqueness correctly; it is simply never read through. It remains open work, tracked in
  [#1258](https://github.com/LIF-Initiative/lif-core/issues/1258), which also has to decide whether
  `idx_org_person` then becomes redundant.

`idx_org_person` is 2 × 255 chars × 4 bytes (utf8mb4) = **3060 bytes, 12 bytes under the same
3072-byte limit** that broke `uq_identity_mapping`. Widening either column, or adding a third to
this index, silently degrades it to `HASH` as well. `02-ddl.sql` carries this warning inline.

**Verifying it, and the trap in doing so.** `EXPLAIN` on an empty or tiny table reports `key=NULL`
whether or not a usable index exists, because the optimizer prefers a scan there — indistinguishable
from the bug. Check `SHOW INDEX` for `Index_type = BTREE`, on a **populated** table, and do not
validate in either direction against an empty one.

No migration is required in dev or demo: ECS mounts EFS at `/mnt/efs`, not `/var/lib/mysql`, so the
MariaDB datadir is ephemeral and `docker-entrypoint-initdb.d` replays `02-ddl.sql` on every task
start. Local docker-compose *does* use named volumes (`mariadb_data_org{1,2,3}`), which hold only
sample seed data, so pick the new schema up with:

```bash
docker compose -f deployments/advisor-demo-docker/docker-compose.yml down -v
```

Re-run this sweep (`--seeds 0,10000,100000,1000000 --batch 100`) to confirm the end-to-end curve
returns to flat at 1M.
