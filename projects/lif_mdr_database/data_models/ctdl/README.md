# CTDL (MDR DataModelId 10) rebuild

<!-- cspell:ignore ceterms ceasn qdata skos rdfs credreg multivalue subclass ctid -->

Inputs, generator and verification for the 2026-10-29 rebuild of the CTDL data model in the
MDR seed (`projects/lif_mdr_database/backup.sql`), executed from `claude_CTDL-work-order-v7`
(rationale in `claude_CTDL-gap-analysis-v2`). The seed is the deliverable; this folder is how it
was produced, so the build can be reproduced or re-applied on a newer seed.

## Files

| File | Role |
|---|---|
| `CTDL-authority-20260927.json` | credreg.net CTDL JSON-LD with `meta:` properties, release 20260927. The authority for classes, properties, domains, ranges, concept schemes and concepts. SHA-256 `5d4410b2…6ff9`. |
| `CTDL-registry-publishing-schema.json` | Credential Registry publishing schema. Read for one field only: `multivalue` per property, which becomes `Array` on attribute rows. SHA-256 `ae2d046e…38e0`. |
| `model_10_before.json` | DataModelId 10 as the seed held it before this build: the rows the cleanup soft-deletes by id, and the only source for the ten attributes carried onto the two retained deprecated classes. |
| `build_ctdl_model.py` | The generator. Verifies both source hashes, applies the work order's rules, and writes the two files below. Standard library only: `python3 build_ctdl_model.py`. |
| `ctdl_model_10_update.sql` | Generated. One transaction: soft-deletes the old model 10 content, then builds the new content through temporary plpgsql helpers that it drops at the end. Idempotent: a second run finds every row in place. |
| `ctdl_model_10_verify.sql` | Work order §6.1 counts and §6.2 structural checks as one query; every row prints expected, actual and `ok`. |
| `build_report.json` | Every count the generator computed, the per-property reference child it chose, and the properties that needed a decision. |

## What the model is

- 142 entities: the 140 `rdfs:Class` nodes in the authority file, plus `Competency` and
  `CompetencyFramework`, deprecated classes retained by decision with `DeprecationDate`
  2021-10-29 and ten attributes carried over from the previous seed.
- Each of the 7,753 domain rows (class × property in `meta:domainFor`) became exactly one row:
  a **Reference association** when at least one declared range is a class in the file
  (5,402 rows), otherwise an **attribute** owned by that class (2,351 rows, UniqueName
  `<Class>.<property>`). Names are the bare local term for `ceterms:`; other namespaces keep
  their prefix (`schema:value`, `elm:Note`, `qdata:relevantDataSet`).
- `DataType` is one of `string`, `boolean`, `number`, `enum`, mapped from the range. Rows whose
  only ranges are outside the model are `string` with `rangeIncludes: … [out of model]` in
  Notes. `skos:Concept` rows are `enum`, linked to a value set when the scheme is in the file.
- 36 concept schemes are value sets; 457 concepts are values (Value = CURIE, ValueName =
  prefLabel).
- `Array` on attribute rows follows the Registry's `multivalue`; references never carry Array,
  and record `multivalue` in their Notes.
- `Required` marks `ctid` and `name` where present, plus the work order's substitute pairs,
  solely so references render with content in the generated schema. It is not CTDL cardinality.
- Entity Notes carry the class hierarchy (`subClassOf:` lines; foreign parents are marked).

A reference association holds one `ChildEntityId`, but a CTDL property may permit several
target classes. The generator lists every permitted target in the association Notes and picks
the column value deterministically: the candidate that is an ancestor (`rdfs:subClassOf`,
within the file) of the most other candidates; on a tie, one that has a Required attribute;
then file order. `build_report.json` lists the pick per property.

## Reproducing or re-applying

1. Restore the previous seed the way `projects/lif_mdr_database/restore.sh` does (the seed,
   then the V1.2+ migrations) into a fresh `postgres:18.6` container.
2. `python3 build_ctdl_model.py` (regenerates the SQL and the report; refuses to run if a
   source hash differs from the work order).
3. `psql -v ON_ERROR_STOP=1 -f ctdl_model_10_update.sql`, then `psql -f ctdl_model_10_verify.sql`
   and confirm every `ok` is `t`.
4. Dump with `pg_dump --no-owner --no-privileges`, restore that dump into a second fresh
   container and dump again; the second dump is the fixed point that goes into `backup.sql`.
5. Regenerate the model 10 schema snapshots on Postgres 16 (CI's engine).

The SQL is keyed by names and by the explicit row ids in `model_10_before.json`, so it can be
re-applied on a newer seed that still contains the same pre-build model 10 rows.
