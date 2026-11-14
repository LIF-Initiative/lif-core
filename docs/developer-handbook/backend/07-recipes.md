# 7. Recipes

The common changes, step by step, with the places people forget.

*Checked against main `2967cb9`, November 2026.* Each recipe names its sources. "Add a field" was run end to end on the local
stack; the others are assembled from the code, recent PRs and the existing guides.

---

## Add a field to the LIF data model

The field lives in the MDR, so this is mostly data, not code ([chapter 3](03-data-model-and-mdr.md)).

1. **Add it in the MDR.** On dev, model 17 holds everything itself (#1388), so you add the attribute to
   model 17 directly. On demo and the local seed, model 17 is still an overlay until #1513, and the rule is: **add
   the attribute to base model 1, then include it in model 17.** The steps below are for the local
   seed. In the MDR UI, or through the API (endpoints at `http://localhost:8012/docs`; log in with
   `POST /login` and send `Authorization: Bearer <access_token>`):
   - `POST /attributes/` with `Name` (camelCase), `UniqueName` (`Person.Name.preferredPronouns`),
     `DataType` (`string`), `DataModelId: 1`, and `EntityId` (the entity in model 1; passing it creates the
     attribute and its link to the entity in one step);
   - `POST /inclusions/` with `ExtDataModelId: 17`, `ElementType: "Attribute"`, `IncludedElementId` (the new
     attribute's `Id`), `LevelOfAccess` (most of 17's inclusions are `Public`), `CreationDate`, and
     `Queryable` / `Modifiable` as needed (these become `x-queryable` / `x-mutable`).

   Verified 11-07 on the local stack with a test field `preferredPronouns` on `Name`: both calls returned
   201; model 17's generated schema showed the field at once; GraphQL showed it only after a restart (next
   step); a query returned it (`null`, since no data has it yet). A reseed ([chapter 1](01-dev-environment.md)) removed it again.
2. **Restart the services that load the schema** (`docker restart lif-graphql-api-org1 …`, semantic
   search): they read it once at startup. The Translator picks it up within 5 minutes (its schema cache), or
   restart it to see it at once.
3. **Seed data**, if the demo should show it: `projects/mongodb/sample_data/<org>/`. The integration tests
   read these files, so they'll expect the new value.
4. **Places that list fields by hand**, which a new field won't reach on its own:
   - the LIF-to-LIF adapter's all-fields queries,
     `components/lif/data_source_adapters/lif_to_lif_adapter/graphql_query_all_fields_org{2,3}.graphql`.
     They are packaged into the Dagster code-location image, so rebuild it after editing them:
     `docker compose up -d --build dagster-code-location`;
   - each planner's `information_sources_config*.yml`, if the field is a new top-level path
     (`Person.<Something>`) that a source supplies.
5. **Know what fetching won't do.** The planner's cache check is per two-level path ([chapter 4](04-follow-the-data.md), step 3).
   A new field under an existing path such as `Person.Name` is only fetched from other sources when the
   learner's cached record has no `Person.Name` at all. To test a fetch locally, reset that org's MongoDB
   ([chapter 1](01-dev-environment.md)) or use a learner who isn't in its seed.
6. **Mappings**: if a source standard should fill the field, add a transformation (next recipe).
7. **Keep the repo's seed in step**: a model change made only in your local MDR is lost on the next
   reseed. To make it part of the seed, see "Change the MDR seed" below.

## Add or change a mapping

1. Edit the transformation in the MDR (UI or API). The expression is **JSONata**:
   [`docs/operations/guides/jsonata-quick-start-guide.md`](../../operations/guides/jsonata-quick-start-guide.md).
2. A new group only takes effect once it's **activated** ([chapter 3](03-data-model-and-mdr.md)). Check with
   `GET /transformation_groups/active_transformations_for_data_models/?source_data_model_id=…&target_data_model_id=…`.
3. No restart needed: the Translator fetches transformations on every request.
4. Don't edit `reference_data/transformations/` by hand; it mirrors the MDR
   (`scripts/import-transformations.sh`).

## Add a data source

- **The adapter contract** (what an adapter receives and returns, how to register it):
  [`docs/operations/guides/creating-a-data-source-adapter.md`](../../operations/guides/creating-a-data-source-adapter.md). Accurate.
- **The end-to-end tutorial**: [`docs/operations/guides/add-data-source.md`](../../operations/guides/add-data-source.md). Useful for the order of steps,
  but **ignore its advice to lower-case** JSONata keys and fragment paths (steps 9 and 11): the model and
  the shipped configs are PascalCase (`Person.Contact`), and lower-case paths match nothing.

The pieces, as [chapter 4](04-follow-the-data.md) traces them:

1. An adapter class (subclass of `LIFDataSourceAdapter`) registered in `ADAPTER_REGISTRY`: either as an
   entry in `_CORE_ADAPTERS` in `components/lif/data_source_adapters/__init__.py`, or with
   `register_adapter(...)` called at startup. `demo_data_source_adapters` provides
   `register_demo_adapters()`, which the orchestrator's `lif_job.py` calls, so an adapter added to its
   `DEMO_ADAPTERS` is registered already. A **new brick** needs its own registration call in `lif_job.py`,
   a line in all four brick lists (the three `projects/dagster_*/pyproject.toml` and
   `orchestrators/dagster/lif-orchestrator/pyproject.toml`, which CI's orchestrator job uses), and a line
   in `dagster_code_location.yml`'s `paths:`.
2. Credentials as environment variables on the **Dagster code-location** container, named
   `ADAPTERS__<ADAPTER_ID>__<INFORMATION_SOURCE_ID>__CREDENTIALS__<KEY>` (upper case, dashes → underscores;
   the keys come from the adapter's `credential_keys`; `get_credentials_for_adapter` in
   `orchestrators/dagster/lif-orchestrator/src/lif_orchestrator/defs/lif_job.py`). In the team's AWS-hosted
   dev and demo they're set in `cloudformation/dagster-ose-taskdef-includes.yml`.
3. If the source isn't LIF-shaped: a source model in the MDR and an active transformation group to the
   target model.
4. An entry in the planner's `information_sources_config*.yml`: `information_source_id`, `adapter_id`,
   `lif_fragment_paths` (PascalCase, two levels), and `translation` if needed. Restart the planner.
   In the team's AWS-hosted dev and demo the file comes from SSM instead: the planner's `entrypoint.sh` writes
   `LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_YAML_SSM` to disk at startup
   (`cloudformation/lif-query-planner-taskdef-includes.yml`).
5. **Check for overlap.** If another source already supplies the same path (org3 supplies
   `Person.Proficiency`, for example), both are asked, and both sets of fragments go to the cache's `/save`.
   How two fragments for one path combine is decided by `compose_with_fragment_list` in
   `components/lif/composer/core.py`; read it, or try it locally, before relying on the result.
6. **Test locally with a stand-in.** The example source (`bases/lif/example_data_source_rest_api/`, its
   adapter in `components/lif/demo_data_source_adapters/`, and the `org1-example-data-source` config entry)
   is a complete small example to copy.

## Change the MDR seed (`backup.sql`)

`projects/lif_mdr_database/backup.sql` is the MDR's seed: every model, mapping and transformation a fresh
local stack starts with, and the data the schema-snapshot tests pin. It is **regenerated with `pg_dump`,
never edited or merged by hand**. Recent seed changes (November 2026) all followed one of three shapes:

| Change | What ships with the change | Example |
|---|---|---|
| Rebuild or add a model | A `projects/lif_mdr_database/data_models/<model>/` folder: build script, `*_update.sql`, `*_verify.sql`, README | CEDS (#1435), CTDL (#1446) |
| Change the MDR's tables | A V1.x migration ("Add an MDR database migration", below) | #1471 |
| Remove or fix data on dev and demo | A script under `scripts/`, run against them (rolls back unless `--apply`); `backup.sql` doesn't change | `scripts/remove_test_data.py` (#1479, #1487) |

The method (written up in [`projects/lif_mdr_database/data_models/ceds/README.md`](../../../projects/lif_mdr_database/data_models/ceds/README.md), "Reproducing or
re-applying"):

1. Restore the current seed into a fresh Postgres the way `restore.sh` does: `backup.sql`, then every
   `V1.*.sql` except V1.1, in version order.
2. Apply your change (your migration, update SQL, or script), and run its verify step.
3. `pg_dump --no-owner --no-privileges` the database. Restore that dump into another fresh database the same
   way and dump again; repeat until two dumps match. That fixed point is the new `backup.sql`.
4. Regenerate the schema snapshots ([`docs/operations/guides/testing.md`](../../operations/guides/testing.md) → Generated-Schema Snapshots) and
   explain in the PR why the generated schemas changed.
5. Run the Postgres-backed tests ([chapter 1](01-dev-environment.md)): they load the seed.

Expect big diffs: adding a column rewrites every row of that table in the dump. If `main`'s `backup.sql`
changes under your PR, don't hand-merge it: merge `main`, rebuild from its seed plus your change, and dump
again.

**How it reaches dev and demo:** `backup.sql` itself is only the local and test seed. The deployed MDRs get
changes through the migration, update SQL or script you shipped with it, applied by someone with access
([chapter 9](09-environments-and-deploys.md)). Seed and migration changes need a maintainer's review before merge, and a maintainer with access to
the team's AWS-hosted dev and demo applies them there afterwards; say in the PR exactly what has to be run.

> [`projects/lif_mdr_database/README.md`](../../../projects/lif_mdr_database/README.md) ("Updating MDR Database Seed Data") also says to copy the dump into
> `V1.1__metadata_repository_init.sql`. That step hasn't been followed since September 2026: `backup.sql`
> has changed six times since V1.1 last did. Ask before doing it.

## Add a new microservice

Follow [`docs/operations/guides/adding-a-new-microservice.md`](../../operations/guides/adding-a-new-microservice.md) (accurate), or the `new-microservice` skill
in `.claude/skills/`. It covers the base and project, the brick lists, `Dockerfile2`, auth wiring with
`lif.auth`, the compose service, and the deploy workflow.

## Add a new component (brick)

1. `uv run poly create component --name <name>` (creates `components/lif/<name>/`).
2. Add it to the root `pyproject.toml` brick list (for development), and to **every project** that will
   use it ([chapter 2](02-codebase-map.md)).
3. Add it to each consuming service's deploy workflow `paths:` filter. `scripts/check_workflow_paths.py`
   fails CI if you miss one.
4. Write a [`README.md`](../../../README.md) in the brick: purpose, public surface, who uses it.
5. Tests under `test/components/lif/<name>/`.

## Add an MDR database migration

**Stop and check with a maintainer first** (the committers are listed in [`docs/COMMITTERS.md`](../../COMMITTERS.md)): this is one
of the repo's stop-and-ask boundaries ([`agent-behavioral-guidelines.md`](../../../agent-behavioral-guidelines.md)). A merged migration does nothing until
someone applies it: V1.6 sat merged and unapplied on both environments (#1226).

0. **Check the live schema first**: the column or table may already exist
   (`\d "TableName"` in the MDR database, [chapter 1](01-dev-environment.md)). Then check `components/lif/mdr_sql_model/` and
   `mdr_dto`, which must change with it.
1. A new file `sam/mdr-database/flyway/flyway-files/flyway/sql/mdr/V1.<next>__<what>.sql`. List the
   directory with `ls … | sort -V` to find the next number (V1.11 is the latest in November 2026).
2. **Idempotent**: `CREATE … IF NOT EXISTS`, `CREATE OR REPLACE`, guarded `ALTER`s. Locally every
   `V1.*.sql` is replayed through `psql` on each reseed, without Flyway's history.
3. **Loop over every schema**: `public` and each `tenant_*` (the seed has `tenant_lif_team`). Copy V1.7's
   `DO $$ … FOR s IN SELECT nspname …` pattern. New tenants are cloned from `public` by `clone_lif_schema`,
   so they pick the change up.
4. Test it:
   - write a test that runs the migration against a real Postgres, alongside the existing ones
     (`test/bases/lif/mdr_restapi/test_v1_11_reference_association_array_sql.py` is a recent example; they need `initdb`, [chapter 1](01-dev-environment.md));
   - reseed locally ([chapter 1](01-dev-environment.md)) and check the restore log for errors beyond the two expected ones;
   - if the change touches the seed, regenerate `backup.sql` ("Change the MDR seed", above).
5. **After merge, someone applies it** to dev and demo by hand:
   [`docs/operations/guides/applying-mdr-migrations.md`](../../operations/guides/applying-mdr-migrations.md). Merging alone changes nothing deployed.

## Change a shared component

1. Find every project that packages it:
   `grep -l 'components/lif/<brick>"' projects/*/pyproject.toml orchestrators/dagster/lif-orchestrator/pyproject.toml`.
2. Name those services in the PR, and run their tests.
3. Check that each one's deploy workflow `paths:` filter covers the brick, or the change won't ship
   (#1171; `scripts/check_workflow_paths.py`).
4. If it touches `mdr_client`, `translator` or `mdr_services`, run the Postgres-backed tests ([chapter 1](01-dev-environment.md)):
   they include the Translator ↔ MDR end-to-end tests that skip without `initdb`.
