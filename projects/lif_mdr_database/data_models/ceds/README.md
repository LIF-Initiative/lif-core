# CEDS (MDR DataModelId 4) rebuild

<!-- cspell:ignore skos rdfs xsd gYear plpgsql restrictions NCESSIDE SCED NAICS -->

Inputs, generator and verification for the rebuild of the CEDS data model in the MDR seed
(`projects/lif_mdr_database/backup.sql`) to CEDS Ontology v14.0.0.0, released 2026-03-11 (#1435).
The seed is the deliverable; this folder is how it was produced, so the build can be reproduced or
re-applied on a newer seed. Every rule the generator applies is written down here.

## Files

| File | Role |
|---|---|
| `build_ceds_model.py` | The generator. Fetches and verifies the sources, applies the rules below, and writes the two generated files. Standard library only: `python3 build_ceds_model.py`. |
| `iso-639-3.tab` | SIL's ISO 639-3 code table, read for its `Part1` column only (see *Value sets*). SHA-256 `07ce5fed…82ed`. Committed because SIL serves it from an unversioned URL. |
| `model_4_before.json` | DataModelId 4 as the seed held it before this build: the rows Phase 1 retires by id, and the legacy value set remediated in place. |
| `ceds_model_4_update.sql` | Generated. One transaction: Phase 1 retires the old content, Phase 2 builds the new content through temporary plpgsql helpers it drops at the end. Idempotent: a second run finds every row in place. |
| `ceds_model_4_verify.sql` | The checks under *Verification* as one query; every row prints expected, actual and `ok`. |
| `build_report.json` | Every count the generator computed, the value-set decisions it made, and the xlsx cross-check. |

### Sources

The two CEDS files are 32 MB together, so they are not committed. The generator downloads each from
its pinned location into `.cache/` (git-ignored) on first run, and refuses to build if a SHA-256
differs:

| File | From | SHA-256 |
|---|---|---|
| `CEDS-Ontology-v14.0.0.0.rdf` | `src/CEDS-Ontology.rdf` at tag `V14.0.0.0` of CEDStandards/CEDS-Ontology (`owl:versionInfo 14.0.0.0`) | `26d782b6…55e3` |
| `CEDS-V14.0.0.0.xlsx` | commit `b5937e8` of CEDStandards/CEDS-Elements | `a92c2d42…f523` |

The RDF is the authority. The xlsx is the tabular extract of the same release and is read only to
cross-check it: every class, concept scheme, property and named individual IRI, and every technical
name, agree (`build_report.json`, `xlsx_cross_check`).

A term is in the model when it carries a `dc:identifier`. That leaves out the ontology's own
metadata vocabulary (`editHistoryEntry`, `localUsageEntry` and the properties that describe them).

## What the model is

- 402 entities, one per CEDS class.
- 2,324 CEDS properties: the 351 whose range is a class are **Reference associations** (473, one
  per domain class); the other 1,973 are **attributes**, each stored once and associated to every
  domain class (2,277 attribute associations, 187 attributes shared by several classes).
- 965 value sets, one per concept scheme, with 11,810 values.
- The `DataModels` row is `CEDS v14` / `14.0.0.0`; its `Notes` name the sources and hashes, and its
  `UseConsiderations` state the cardinality and reference rules below.

Issue #1435 specified the 351 class-ranged properties as attributes with `DataType` `entity` and a
`TargetEntityId`. That construct is deprecated (portable-file spec §11) and export refuses it
(`NOT_MIGRATED`), so they are modeled as references instead, as the CTDL rebuild does; that is why
the attribute and attribute-association counts are the issue's 2,324 and 2,750 less 351 and 473.

## Rules

### Naming

`Name` and `UniqueName` are the technical name (`skos:notation`), with the `(Deprecated)` prefix
and any whitespace removed (`NCESSIDEStandard Error` becomes `NCESSIDEStandardError`). `-` and `*`
are kept (`hasO*NET-SOCOccupationType`), as other seed models already do. Where the stored name
differs from the notation, the element's Notes carry `CEDS v14 skos:notation: <original>`.

Two pairs of properties share a technical name. Each keeps it as `Name` and gets a `_<dc:identifier>`
suffix wherever a key must be unique: the attribute `UniqueName` for `LearningResourceIdentifier`
(`_P001750`, `_P002027`; different classes), and the association `Name` for
`hasIndividualizedProgramMeetingAttendee` (`_P600161`, `_P600553`; both on
`IndividualizedProgramMeeting`, so the names would otherwise collide under one parent). No other
parent holds two keys with one name.

### Typing

Every property has exactly one range. `DataType` is one of `enum`, `string`, `number`, because the
schema generator copies it into the OpenAPI `type`:

| Range | `DataType` | Count |
|---|---|---|
| a concept scheme | `enum`, linked to its value set | 994 |
| `xsd:string`, `xsd:token`, `xsd:anyURI`, `xsd:date`, `xsd:dateTime`, `xsd:time`, `dc:format` | `string` | 727 |
| `xsd:decimal`, `xsd:int`, `xsd:integer`, `xsd:nonNegativeInteger`, `xsd:byte`, `xsd:gYear` | `number` | 252 |
| a CEDS class | a Reference association, not an attribute | 351 |

What the MDR type cannot carry goes in the attribute's Notes: `format: xsd:<type>` for every range
other than `xsd:string` and `xsd:decimal` (`rangeIncludes: dc:format` for the one `dc:format` range),
and the CEDS facets `textFormat`, `maxLength`, `minLength`, `minInclusive`, `maxInclusive`,
`decimalPlaces` under their own names. Notes also carry `property: P######`, the scheme for an enum,
and `domainIncludes:` for an attribute shared by several classes. `Description` is
`skos:definition` (else `dc:description`); `UseConsiderations` is `rdfs:comment`.

### References

`Placement` is `Reference`, `Relationship` is NULL, and `Name` is the property's technical name.
The child is the property's single range; six properties point back at their own class. Notes carry
the property id, its description and any use considerations. References are not rendered with
content: the schema generator copies only a referenced entity's Required properties, and CEDS
declares none, so every reference renders as an empty object. Rendering references is a schema
generator concern, not something this seed fakes with invented `Required` values.

### Cardinality

CEDS declares no cardinality. `Required` and `Array` are NULL on every entity and attribute, and
every association has `Array` `false` (a NULL association `Array` means "not computed yet" to the
MDR).

### Entities and hierarchy

Six pre-build entities keep their ids and are remediated in place, because the same CEDS class
exists under the same name: `AssessmentForm` (14), `AssessmentPerformanceLevel` (15),
`AssessmentResult` (18), `AssessmentRegistration` (19), `Employment` (198), `ProgramParticipation`
(307). The other 19 are retired (`Deleted = true`; ids are never reused); 12 of them get a
`UseConsiderations` note naming the CEDS v14 classes that replace them (`RETIRED_REPLACEMENTS` in the
generator), and the other seven have no CEDS v14 counterpart. Every old attribute and attribute
association is retired, including those on the six kept entities.

Entity Notes carry `class: C######`, one `subClassOf:` line per parent class (398 lines), and one
`restriction:` line per `owl:Restriction` (18). The hierarchy is recorded, not modeled: there are no
associations for it and properties are not inherited down it.

### Value sets

Each concept scheme becomes a value set named by its technical name, with `scheme: C######` in
Notes. Each member becomes a value with `Value` = `skos:notation` (the code), `ValueName` =
`skos:prefLabel`, `Description` = `skos:definition`, `Source` `CEDS v14`, and `concept: NI…` in
Notes.

- **Which members load.** Schemes with at most 100 members load in full. Of the nine larger ones,
  eight load in full by decision (`SCEDCourseCode` 1,753, `EmploymentNAICSCode` 1,012,
  `TribalAffiliation` 577, `ISO6392LanguageCode` 487, `CountryCode` 249,
  `FinancialExpenditureObjectCode` 154, `ISO6395LanguageFamily` 115, `FinancialAccountRevenueCode`
  104). `ISO6393LanguageCode` (7,916) is capped to the 183 codes that have an ISO 639-1 equivalent,
  meaning a `Part1` code in `iso-639-3.tab` (SIL lists 184; CEDS has no `zul`), and its
  `UseConsiderations` say so. Two schemes have no members in the source and are empty value sets
  (`CIPCode`, `NCESCollegeCourseMapCode`).
- **A code listed twice** is loaded once: the non-deprecated member, then the one with a real
  definition (not CEDS's `PutDefinitionHere`), then the first in file order. Three are dropped
  (`EnrollmentStatus` `01814`, `K12StaffClassification` `SchoolCounselors`, `ISO6392LanguageCode`
  `dgr`); the report lists them.
- **A label shared by two codes** becomes `Label (code)`, since `ValueName` is unique within a value
  set (`Business Law (04164)`, `Business Law (12054)`). Notes keep the original `prefLabel:`.

The legacy value sets: the nine bound to the old attributes (`Voc1`–`Voc3`, `Voc6`–`Voc9`,
`courseStandardAlignment`, `participationStatus`) are retired with their 583 values and the 583
value mappings from those values to LIF. `StateAbbreviation` (277) is the one legacy set whose name
is also a CEDS v14 scheme. It is remediated in place, so the 62 CEDS → LIF mappings on its values
keep their rows: each legacy value is matched to the CEDS member by code (all 62 match) and takes
its label, and CEDS adds `BI`, `DD`, `DO`. The other 67 legacy value sets are left as they were,
with their CEDS → LIF crosswalk. Transformation group 3 (`CEDS_LIF`) is not touched; its one live
transformation (1189) references no model-4 attribute.

### Deprecation

Three properties, one scheme and 25 members carry `owl:deprecated` (30 members in the source; five
are among the ISO 639-3 codes the cap leaves out). Each gets `DeprecationDate` 2026-03-11 (the v14
release) and `Deprecated in CEDS: <statement>` in its `UseConsiderations` (Notes, for the one
deprecated property that is a reference), the statement being the CEDS edit-history entry that
records the deprecation.

## Retirement (Phase 1)

Soft deletes do not cascade, so each table is named: the 583 value mappings, 583 values and 9 value
sets above; the 187 old attribute associations and 187 old attributes; the 19 retired entities. Every
statement names the exact row ids from `model_4_before.json` **and** is guarded to model 4
(`"DataModelId" = 4`, or membership in model 4's entities or retired values), so the SQL cannot
touch another model's rows on a database whose ids differ from the seed's. `tenant_lif_team` keeps
its own copy of the pre-build model 4.

## Verification

`ceds_model_4_verify.sql` checks these counts: 402 entities, 6 kept ids live, 19 retired, 12 with a
replacement note; 1,973 attributes (994 `enum`, 727 `string`, 252 `number`), 2,277 attribute
associations, 187 shared attributes; 473 references across 351 properties, 6 self references;
965 CEDS value sets with 11,810 values, 183 ISO 639-3 values with the cap stated, `StateAbbreviation`
with 65 values and 62 live mappings, 67 untouched legacy sets; 9 / 583 / 583 retired sets, values
and mappings, and no live mapping into or out of a retired value; 187 retired attributes;
deprecation on 2 attributes, 1 reference, 1 value set and 25 values, and nowhere else; group 3 with
its one live transformation; `tenant_lif_team` model 4 unchanged.

Structural checks: unique entity and attribute UniqueNames; entity Name = UniqueName; exactly the
two `_P######` attribute UniqueNames and two reference Names; no key used twice under one parent; EAA
Name = attribute Name; no NULL association Name or Array, and none `true`; every reference
`Reference` with NULL Relationship and a live child; no unassociated attribute; no Required or Array
on elements; no NULL element flags; no NULL, `entity` or other `DataType`, no `TargetEntityId`; every
enum linked to a CEDS value set and no other type linked; no duplicate ValueName or code in a CEDS
value set; temporary functions dropped.

Round trip, run in-process against the repo's portability code when the seed was built: export
model 4 (succeeds: no `NOT_MIGRATED`), edit `Details.Version`, import, export again; the second export
is byte-equal to the first excluding Details. The schema route renders 402 root schemas.

## Reproducing or re-applying

1. Restore the previous seed the way `projects/lif_mdr_database/restore.sh` does (the seed, then the
   V1.2+ migrations) into a fresh `postgres:18.6` container.
2. `python3 build_ceds_model.py` (downloads the CEDS sources on first run; regenerates the SQL and
   the report).
3. `psql -v ON_ERROR_STOP=1 -f ceds_model_4_update.sql`, then `psql -f ceds_model_4_verify.sql` and
   confirm every `ok` is `t`.
4. Dump with `pg_dump --no-owner --no-privileges`, restore that dump into a fresh container the way
   `restore.sh` does and dump again; repeat until two dumps match. That fixed point goes into
   `backup.sql`.
5. Regenerate the model 4 schema snapshots on Postgres 16 (CI's engine):
   `LIF_UPDATE_SCHEMA_SNAPSHOTS=1 uv run pytest test/bases/lif/mdr_restapi/test_schema_snapshots.py`.

The SQL is keyed by names and by the explicit row ids in `model_4_before.json`, so it can be
re-applied on a newer seed that still contains the same pre-build model 4 rows.
