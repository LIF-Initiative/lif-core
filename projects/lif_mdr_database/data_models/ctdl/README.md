# CTDL (MDR DataModelId 10) rebuild

<!-- cspell:ignore ceterms ceasn qdata skos rdfs credreg multivalue subclass ctid langString anyURI -->
<!-- cspell:ignore vann dct audLevel -->

Inputs, generator and verification for the rebuild of the CTDL data model in the MDR seed
(`projects/lif_mdr_database/backup.sql`) from the CTDL release of 2026-09-27. The seed is the
deliverable; this folder is how it was produced, so the build can be reproduced or re-applied on a
newer seed. Every rule the generator applies is written down here; nothing else is needed to read
the generator or the seed's model-10 rows.

## Files

| File | Role |
|---|---|
| `CTDL-authority-20260927.json` | credreg.net CTDL JSON-LD with `meta:` properties, release 20260927. The authority for classes, properties, domains, ranges, concept schemes and concepts. SHA-256 `5d4410b2…6ff9`. |
| `CTDL-registry-publishing-schema.json` | Credential Registry publishing schema. Read for one field only: `multivalue` per property, which becomes `Array` on attribute rows. SHA-256 `ae2d046e…38e0`. |
| `model_10_before.json` | DataModelId 10 as the seed held it before this build: the rows the cleanup soft-deletes by id, the crosswalk the build re-points, and the only source for the ten attributes carried onto the two retained deprecated classes. |
| `build_ctdl_model.py` | The generator. Verifies both source hashes, applies the rules below, and writes the two files beneath. Standard library only: `python3 build_ctdl_model.py`. |
| `ctdl_model_10_update.sql` | Generated. One transaction: soft-deletes the old model 10 content, then builds the new content through temporary plpgsql helpers that it drops at the end. Idempotent: a second run finds every row in place. |
| `ctdl_model_10_verify.sql` | The counts and structural checks under *Verification* as one query; every row prints expected, actual and `ok`. |
| `build_report.json` | Every count the generator computed, the per-property reference child it chose, the rebuilt crosswalk, and the properties that needed a decision. |

## What the model is

- 142 entities: the 140 `rdfs:Class` nodes in the authority file, plus `Competency` and
  `CompetencyFramework`, deprecated classes retained by decision (see *Retained deprecated classes*).
- Each of the 7,753 domain rows (class × property in `meta:domainFor`) became exactly one row:
  a **Reference association** when at least one declared range is a class in the file
  (5,402 rows), otherwise an **attribute** owned by that class (2,351 rows, UniqueName
  `<Class>.<property>`). A property that places on several classes gets one row per class, so
  `Required` can differ by class.
- 36 concept schemes are value sets; 457 concepts are values.
- Entity Notes carry the class hierarchy; association and attribute Notes carry what the table
  columns cannot (permitted targets, `multivalue`, out-of-model ranges, target schemes).

## Rules

### Naming

Names are the bare local term for `ceterms:` terms; every other namespace keeps its prefix
(`schema:value`, `elm:Note`, `qdata:relevantDataSet`), so those OpenAPI keys contain a colon. The
generator asserts that no class holds two properties sharing a bare name. Reference associations
are named by the property (`accreditedBy`, `ownedBy`), which is the source's own key, not the MDR's
`Ref<Entity>` convention; the portable-file spec does not check the naming convention on import.

### Typing

`DataType` is one of `string`, `boolean`, `number`, `enum`, because the schema generator copies it
into the OpenAPI `type`. The map from `schema:rangeIncludes`:

| Range | `DataType` |
|---|---|
| `xsd:string`, `rdf:langString`, `rdfs:langString`, `rdfs:Literal`, `xsd:language`, `xsd:anyURI` | `string` |
| `xsd:boolean` | `boolean` |
| `xsd:integer`, `xsd:decimal`, `xsd:float` | `number` |
| `xsd:date`, `xsd:dateTime`, `xsd:duration`, `schema:Date`, `schema:Duration` | `string`, with `format:` in Notes |
| `skos:Concept` | `enum`, linked to the value set when the file carries the scheme |
| `skos:ConceptScheme`, `rdfs:Resource`, `schema:WebPage`, `rdf:Statement`, any class not in the file | no resolvable range: `string`, with `rangeIncludes: … [out of model]` in Notes (140 rows across 13 properties) |

A property with ranges of more than one kind takes the widest, `string`, with every range in Notes
(`leftSource` and `rightSource`: `rdf:Property`, `rdfs:Class`, `rdfs:Literal`, `skos:Concept`).
`skos:ConceptScheme` is not `skos:Concept`; those rows are never enums. An `enum` whose scheme the
file does not carry has no `ValueSetId` (96 rows, plus the four retained type attributes).

### References

A range *resolves* if and only if it is the `@id` of an `rdfs:Class` node in the authority file.
A domain row is a Reference association when at least one of its property's ranges resolves,
otherwise an attribute; the rule is applied per range, not per property. `Relationship` is NULL,
`Placement` is `Reference`, and the association `Name` is the property.

A CTDL property may permit several target classes, but `EntityAssociation` holds one
`ChildEntityId`. The association Notes list every permitted target (`permittedTargets:`), and the
column takes one, chosen deterministically: the candidate that is an `rdfs:subClassOf` ancestor
(within the file) of the most other candidates; on a tie, one that has a Required attribute, so the
reference renders content; then file order. `build_report.json` lists the pick per property
(215 properties, 51 distinct children). `isSimilarTo` (76 in-model targets plus 7 other ranges) is
a reference with child `Credential`.

A range on a reference row that neither resolves nor is a literal or `skos:Concept` is noted as
`unresolvedRanges:` (295 rows across 21 properties; `ceterms:TransferValueAgreement` is one, a
range of `owns` with no class node in the file, recorded as the file has it). A literal or concept
range on a reference row is noted as `droppedRanges:`, since a reference cannot carry it.

### Array

CTDL declares no cardinality. `Array` on the **Attributes row** follows `multivalue` in the Registry
publishing schema (`Yes` / `No`; NULL for the three rows whose property the Registry lacks:
`CredentialPerson.givenName`, `.familyName`, `.honorificSuffix`). The schema generator reads Array
from the Attributes row, so that is where it must be written.

Both association tables carry a **boolean** `Array`, never NULL: the MDR reads a NULL association
Array as "not computed yet" and recomputes it on the next edit of the child. An attribute
association mirrors its attribute row (`false` where that is NULL). A reference association follows
the property's `multivalue` (4,929 `true`, 321 `false`, and `false` for the 152 whose property the
Registry lacks); its Notes record the flag as well. The schema generator does not read association
Array today, so this changes no generated schema (rendering references as arrays is the #1429
follow-up).

### Required

`Required` exists solely so references render: the schema generator copies only a referenced
entity's required properties, so an entity with nothing required renders as an empty object. It
does not assert CTDL cardinality. `ctid` and `name` are `Required` wherever present; classes with
neither get a substitute pair:

| Class | Required |
|---|---|
| `AlignmentObject`, `CredentialAlignmentObject` | `targetNode`, `targetNodeName` |
| `CredentialPerson` | `givenName`, `familyName` |
| `IdentifierValue` | `identifierValueCode`, `identifierTypeName` |
| `JurisdictionProfile` | `description`, `globalJurisdiction` |
| `PayProfile` | `schema:value`, `currency` |
| `RevocationProfile` | `description`, `revocationCriteriaDescription` |
| `ValueProfile` | `schema:value`, `creditUnitType` |
| `schema:QuantitativeValue`, `schema:MonetaryAmount` | `schema:value`, `schema:description` |
| `elm:Note` | `elm:noteLiteral` |
| `DurationProfile` | `exactDuration`, `minimumDuration`, `maximumDuration` (alternatives in CTDL; accepted under the rendering reading) |

Only attribute rows can be Required (`Assessment`'s one property is a reference, so it stays
empty). The ten propertyless classes get nothing and render empty by design. References to
`LearningResource` and `CredentialAssertion` are the six that render as empty objects.

### Hierarchy

Each entity's Notes carry one `subClassOf:` line per parent; a parent that is not in the model is
suffixed `[foreign — not modeled]`. 96 classes have a parent, 7 of them more than one, 44 have none,
56 have no parent inside the model. Foreign parents not modeled: `schema:CreativeWork`,
`schema:Person`, `schema:Intangible`, `schema:StructuredValue`, `schema:AlignmentObject`,
`schema:EducationalOccupationalProgram`, `dct:Agent`.

### Foreign classes

Three classes outside `ceterms` ship in the CTDL serialization and are modeled as a deliberate
exception, with `SourceModel` `CTDL` and the Notes line `retained by exception`:
`schema:QuantitativeValue`, `schema:MonetaryAmount`, `elm:Note`. `ValueProfile` is a subclass of
`schema:QuantitativeValue`, which therefore resolves.

### Retained deprecated classes

`ceterms:Competency` and `ceterms:CompetencyFramework` are not in the authority file (it carries
only current terms). They are retained by decision with `DeprecationDate` `2021-10-29T00:00:00Z`
and Notes naming the successor (`ceasn:Competency`, `ceasn:CompetencyFramework`), the change
reason, and Credential Engine Schema-Development issue 785. Only genuine `ceterms` attributes were
carried over from the pre-build rows in `model_10_before.json`, typed by the map above; the
`ceasn-` ones were dropped.

| Entity | Attributes (pre-build Attributes row) |
|---|---|
| `CompetencyFramework` | `source` (382), `name` (383), `description` (384), `inLanguage` (391) |
| `Competency` | `codedNotation` (396), `inLanguage` (401), `environmentalHazardType` (406), `performanceLevelType` (407), `physicalCapabilityType` (409), `sensoryCapabilityType` (410) |

Neither entity is the child of any reference.

### Properties that never place

13 properties have no domain among the 140 classes and are not created: `affiliatedAgent`,
`endTime`, `facetedDescription`, `inAlignmentMap`, `inQualificationsFramework`,
`indicativeCredentialType`, `logicalOperator`, `spatialCoverage`, `startTime`,
`targetCompetencyOf`, `temporalCoverage`, `owl:sameAs`, `qdata:dataProvider`.

### Value sets

The 36 concept schemes become value sets named by the scheme's local name; each concept is a value
with `Value` = CURIE (`audLevel:SecondaryLevel`), `ValueName` = prefLabel, `Description` =
definition, `UseConsiderations` = usage note, `Source` `CTDL`. 16 attribute-typed properties
across 21 rows link to a value set; `meta:targetScheme` on a reference row goes into its Notes.

The pre-build seed had one live CTDL → LIF crosswalk: 7 rows from the old
`courseApplicableEducationLevel` set (118) to the LIF set of the same name (52). Phase 1 soft-deletes
them with their set; Phase 2 rebuilds them from the new `AudienceLevel` set, matching each old value
(`audLevel-X`) to its concept CURIE (`audLevel:X`) and keeping the same target value, so the
crosswalk still exports.

## Cleanup (Phase 1)

Soft deletes do not cascade, so each table is named: transformation group 9 (already deleted in the
seed) with its 176 transformations and 352 transformation attributes; the 27 value sets, 112 values
and 115 mapping rows; the 14 entities, 140 attributes and 140 attribute associations. Every
statement names the exact row ids from `model_10_before.json` **and** is guarded to model 10
(`"DataModelId" = 10`, or membership in model 10's entities, values or transformation group), so the
SQL cannot touch another model's rows on a database whose ids differ from the seed's. LIF value set
52 is untouched.

## Verification

`ctdl_model_10_verify.sql` checks these counts: 142 entities; 5,402 reference associations; 2,361
attributes and attribute associations (2,351 + 10 retained); 96 entities with hierarchy notes;
10 propertyless entities; 36 value sets with 457 values; attribute Array 921 Yes / 1,437 No / 3
null (915 / 1,433 / 3 on domain rows); reference Notes multivalue 4,929 true / 321 false /
152 unknown, and 4,929 reference associations with Array `true`; 140 no-resolvable-range rows across 13 properties; 295 unresolved-range rows across
21 properties; 0 null DataType; 21 value-set links across 16 properties; 27 / 112 / 115 old
value-set rows and 14 / 140 old entity and attribute rows soft-deleted; 7 live crosswalk rows;
242 Required attributes; 2 deprecated entities and 10 deprecated attributes; 100 enums without a
value set.

Structural checks: one child per Name per parent; no duplicate, orphaned or shared attribute
associations; no `entity` or unknown `DataType`, no `TargetEntityId`; every association
`Reference` with NULL Relationship; no NULL association Name or Array; no root
entity Array or Required; model 10 live under its name; class-prefixed unique UniqueNames; attribute
association Name and Array equal to the attribute row's; temporary functions dropped.

Round trip (run in-process against the repo's portability code when the seed was built): export
the model, edit `Details.Version`, import into a fresh restore, export again; the second export is
byte-equal to the first excluding Details, and the schema route renders 142 root schemas with every
reference a non-empty object except the six that target propertyless classes.

## Reproducing or re-applying

1. Restore the previous seed the way `projects/lif_mdr_database/restore.sh` does (the seed,
   then the V1.2+ migrations) into a fresh `postgres:18.6` container.
2. `python3 build_ctdl_model.py` (regenerates the SQL and the report; refuses to run if a
   source hash differs from the pinned one).
3. `psql -v ON_ERROR_STOP=1 -f ctdl_model_10_update.sql`, then `psql -f ctdl_model_10_verify.sql`
   and confirm every `ok` is `t`.
4. Dump with `pg_dump --no-owner --no-privileges`, restore that dump into a second fresh
   container and dump again; the second dump is the fixed point that goes into `backup.sql`.
5. Regenerate the model 10 schema snapshots on Postgres 16 (CI's engine).

The SQL is keyed by names and by the explicit row ids in `model_10_before.json`, so it can be
re-applied on a newer seed that still contains the same pre-build model 10 rows.
