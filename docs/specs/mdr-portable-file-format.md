# MDR Portable File Format

<!-- cspell:ignore valuename valuesetid PESC OSID -->

**Status:** Draft — for review before implementation. [§13](#13-open-questions) lists what is still open.
**Format version:** 1
**Tracking issue:** [#1333](https://github.com/LIF-Initiative/lif-core/issues/1333) (epic [#1223](https://github.com/LIF-Initiative/lif-core/issues/1223))

This spec defines the files that move MDR content between installs, and the converter that reads
and writes them. Three kinds of file:

- a **model file**: one data model;
- a **mapping-group file**: one transformation group;
- a **crosswalk file**: value mappings from one value set to another.

The files are the contract, and the database is an implementation detail behind them.

The format describes a **simplified MDR data model** in which every model is self-contained, per
[ADR `data_model/0004`](../design/adr/data_model/0004-retire-overlays-variants-as-copies.md). Most of what it leaves out exists in the database today, and §11 lists each removed feature as **deprecated**, with how much existing content
it affects. Seed figures are counted on `backup.sql` at `main` @ `497c863`, live rows only. They are
evidence, not part of the contract.

---

## 1. The model in one page

- **There is one kind of model, and every model is self-contained.** A model does not inherit from,
  layer on, or include another model
  ([ADR `data_model/0004`](../design/adr/data_model/0004-retire-overlays-variants-as-copies.md)).
  A variant of a model is a copy of it.
- **A model is made of** entities, attributes and value sets. An **entity** is a node: it holds other
  entities and attributes, and has no value of its own. An **attribute** is a leaf: it holds a
  value of a `DataType`, optionally drawn from a value set. Every entity and attribute carries
  `LevelOfAccess`, `Queryable` and `Modifiable`.
- **Associations** place one element under another, within the same model. Each association has a
  required `Name`, the key the child appears under. An association to an entity either **directly
  contains** the child (the legacy `Embedded` placement) or **references** it (the legacy
  `Reference` placement). Containing associations have no cycles, so a recursive structure
  always goes through a reference.
- **Every reference resolves inside its own model.** An element reference never names another
  model.
- **Lineage, not inheritance.** A copy may record the identity of the model it was copied from.
  Lineage carries no behavior: the source need not be installed, and changing or deleting it does
  not affect the copy.

---

## 2. Terms

| Term | Meaning |
|---|---|
| **Model identity** | `(Name, Version, ContributorOrganization)`. All three are required and non-empty. `Version` is stored in the `DataModelVersion` column. The database enforces their uniqueness with the unique index `datamodels_active_ux` on the `DataModels` table. |
| **Lineage** | The identity of the model a copy was made from (`CopiedFrom`, §5.2). |
| **Live row** | A row whose `Deleted` is not true. Soft-deleted rows are never exported, and references to them count as absent. |

---

## 3. Guarantees

1. **No row IDs.** No field holds a database row ID, and nothing in a file is looked up by ID. A
   file that contains one is refused with `ROW_ID_PRESENT`.
2. **Create-only, all or nothing.** Import creates new rows and never changes existing ones. It
   either succeeds completely or leaves no rows behind. ADR `metadata_repository/0009` expects
   import to update a mapping in place by `(group, target path)`; [ADR `metadata_repository/0010`](../design/adr/metadata_repository/0010-mapping-paths-use-association-names.md) defers that to the
   merge and replace import modes (NEW-J in the [portability plan](../operations/proposals/mdr-import-export-portability.md)).
3. **Refused by name.** Anything the converter cannot carry faithfully is refused with a named
   error from [§10](#10-errors), naming the element. Nothing is silently skipped, defaulted or
   guessed.
4. **Canonical export.** The same rows always export to the same bytes ([§9](#9-canonical-form)).
5. **Round trip.** For a canonical file `A`: import `A` into install 1 and export it to get `B`;
   import `B` into install 2 and export it to get `C`. Then `A == B == C`, byte for byte.

---

## 4. Envelope, versioning and references

### 4.1 Envelope

Every file is a JSON object whose first key is `Format`:

```json
"Format": { "Type": "lif-mdr-model", "Version": 1 }
```

| `Format` field | Meaning |
|---|---|
| `Type` | `"lif-mdr-model"`, `"lif-mdr-mapping-group"` or `"lif-mdr-crosswalk"` |
| `Version` | The integer `1` |

`Format` holds only these two fields. Anything else in it, such as an export time or the exporting
install, is refused with `FIELD_UNKNOWN`: it would change on every export and break the canonical
form (§9) and the round trip (§3).

### 4.2 Versioning

- **Parsing is strict.** A key that the file's format version does not define is refused with
  `FIELD_UNKNOWN`, because dropping it silently would make the import lossy. A key listed as
  deprecated in [§11](#11-deprecated) is refused with `DEPRECATED_FIELD`, naming the key.
- **Every change bumps `Format.Version`**, including adding an optional field. A converter states
  which versions it reads, and refuses any other with `FORMAT_VERSION_UNSUPPORTED`.
- A new version states how each older version maps into it. The converter keeps reading every
  version it has written, unless this spec retires one.
- Files with no `Format`, or a `Format.Type` this spec does not define, are refused with
  `FORMAT_UNKNOWN`. That includes today's
  `DataModelExportDTO` export and today's transformation-group export, which stay on their current
  endpoints.

### 4.3 Element references

| Reference | Meaning |
|---|---|
| `{ "Entity": "Student" }` | The entity with `UniqueName` `Student` in the file's model |
| `{ "Attribute": "Student.ssn" }`, `{ "ValueSet": "Gender" }` | The same, for an attribute or a value set |

In a model file, a reference is resolved in the file's own model, and has no way to name another
one. The one exception is a crosswalk (§7), whose two value-set references each name their model by
identity. If no live element with that key exists, the reference is refused with
`REFERENCE_UNRESOLVED`.

**Element keys** follow the database's unique indexes:

| Element | Key | Database unique index |
|---|---|---|
| Entity | `UniqueName` within its model | `uq_entities_uniquename_datamodelid_active` |
| Attribute | `UniqueName` within its model | `uq_attributes_uniquename_datamodelid_active` |
| Value set | `Name` within its model | `ux_valuesets_name_datamodelid_active` |
| Value | `ValueName` within its value set | `ux_valuesetvalues_valuename_valuesetid_active` |

Entities and attributes are keyed by `UniqueName`, not `Name`. `Name` is not unique: there are 234
duplicate `(model, Name)` pairs among attributes alone.

Keys are unique per kind: an entity and an attribute in the same model may share a `UniqueName`,
because every reference states its kind. The seed has one such pair (`Taxonomy.Classifier` in
model 5).

---

## 5. Model file

### 5.1 Shape

```json
{
  "Format": { "Type": "lif-mdr-model", "Version": 1 },
  "Details": { … },       // this model's identity, its lineage, and descriptive fields
  "ValueSets": [ … ],     // the model's value sets, each with its values
  "Entities": [ … ],      // the model's entities
  "Attributes": [ … ],    // the model's attributes
  "Associations": [ … ]   // links that place a child element under a parent entity
}
```

Every top-level key is always present; an empty list is written as `[]`. A model file contains
exactly one model, and it is complete on its own: importing it needs no other model to be
installed.

All the field tables below share one format. **Req.** means the field must be present.

### 5.2 `Details`

| Field | Req. | Meaning |
|---|---|---|
| `Name`, `Version`, `ContributorOrganization` | ✓ | This model's identity |
| `CopiedFrom` | | Lineage: the identity (`Name`, `Version`, `ContributorOrganization`) of the model this one was copied from, written inline. Absent means the model is not a copy. The named model need not be installed, and is not checked |
| `Description`, `UseConsiderations`, `Notes`, `Contributor`, `State`, `Tags` | | Descriptive text |
| `ActivationDate`, `DeprecationDate` | | Timestamps |

An import is refused with `MODEL_EXISTS` when a live model with the same identity is already
installed. `CopiedFrom` is set once, when the copy is made; editing it is not part of this format.
Schema diff uses it as the default model to compare against ([ADR `data_model/0004`](../design/adr/data_model/0004-retire-overlays-variants-as-copies.md)).

### 5.3 Owned elements: `ValueSets`, `Entities`, `Attributes`

**Value set**

| Field | Req. | Meaning |
|---|---|---|
| `Name` | ✓ | Key |
| `Values` | ✓ | List of values (below) |
| `Description`, `UseConsiderations`, `Notes`, `Contributor`, `ContributorOrganization`, `Tags` | | Descriptive text |
| `ActivationDate`, `DeprecationDate` | | Timestamps |

**Value**

| Field | Req. | Meaning |
|---|---|---|
| `ValueName` | ✓ | Key. A value without one is refused with `VALUE_NAME_MISSING` |
| `Value` | ✓ | The code itself. It may differ from `ValueName`, as it does for 1,269 seed values |
| `Description`, `UseConsiderations`, `Source`, `Notes`, `Contributor`, `ContributorOrganization` | | Descriptive text |
| `ActivationDate`, `DeprecationDate` | | Timestamps |

A value set need not be used by any attribute. In the seed, 186 of 235 live value sets are not,
including 89 of the 106 source value sets that value mappings refer to (§7).

**Entity**

| Field | Req. | Meaning |
|---|---|---|
| `UniqueName` | ✓ | Key |
| `Name` | ✓ | Display name. It is also the key the entity appears under when it has no parent |
| `LevelOfAccess` | ✓ | `Public`, `Internal`, `Restricted` or `Private` |
| `Queryable`, `Modifiable` | ✓ | Booleans. They become `x-queryable` and `x-mutable` in the generated schema, which GraphQL and semantic search use to build filters and mutations |
| `Required` | | Boolean; absent means `false`. Puts the element in its parent's `required` list |
| `Description`, `UseConsiderations`, `SourceModel`, `Notes`, `Contributor`, `ContributorOrganization`, `Tags`, `Common` | | Descriptive text; `Common` is a nullable boolean |
| `ActivationDate`, `DeprecationDate` | | Timestamps |

**Attribute**

| Field | Req. | Meaning |
|---|---|---|
| `UniqueName` | ✓ | Key |
| `Name` | ✓ | Display name |
| `DataType` | ✓ | Any data type except `entity` ([§11](#11-deprecated)) |
| `ValueSet` | | Value-set reference ([§4.3](#43-element-references)) to a value set in this model |
| `LevelOfAccess`, `Queryable`, `Modifiable` | ✓ | As for entities |
| `Required` | | Boolean; absent means `false`. Puts the element in its parent's `required` list |
| `Description`, `UseConsiderations`, `SourceModel`, `Example`, `Notes`, `Contributor`, `ContributorOrganization`, `Tags`, `Common` | | Descriptive text |
| `ActivationDate`, `DeprecationDate` | | Timestamps |

Every attribute must be the child of at least one association, otherwise the import is
refused with `UNASSOCIATED_ATTRIBUTE`. An attribute with no association has no place in the
generated schema.

### 5.4 `Associations`

An association places a child element, an entity or an attribute, under a parent entity:

```json
{ "Parent": { "Entity": "Course" }, "Child": { "Entity": "Organization" }, "Name": "AccreditedBy", "Reference": true }
{ "Parent": { "Entity": "Student" }, "Child": { "Attribute": "Student.lunchStatus" }, "Name": "lunchStatus" }
```

| Field | Req. | Meaning |
|---|---|---|
| `Parent` | ✓ | Reference to an entity in this model |
| `Child` | ✓ | Reference to an entity or attribute in this model |
| `Name` | ✓ | The key the child appears under in its parent. By convention PascalCase for an entity child and camelCase for an attribute child ([data-model-rules.md](data-model-rules.md)). The convention applies to new models and is not checked on import: migrated names keep today's keys, and 36 of the 49 relationships set in the seed start lowercase (`basisLegalCode`, `awardedByRefOrganization`) |
| `Array` | | Boolean; absent means `false`. Makes the child a list under this parent, in the generated schema and in GraphQL. It belongs to the association, so a shared entity can be a list under one parent and single under another (Q7) |
| `Reference` | | `true` when the parent points to the child rather than containing it. Allowed only when the child is an entity; on an attribute child it is refused with `REFERENCE_INVALID`. Absent means the parent directly contains the child |
| `Notes`, `Contributor`, `ContributorOrganization` | | Descriptive text |
| `ActivationDate`, `DeprecationDate` | | Timestamps |

The rules:

1. **A parent has at most one child under a given `Name`**, otherwise the import is refused with
   `ASSOCIATION_NAME_TAKEN`. The same child may appear under one parent more than once, under
   different names; this is how roles are expressed (`AccreditedBy` and `ApprovedBy` are both
   `Organization`).
2. **No containment cycles.** The containing associations (those without `Reference`) must have
   no cycle, including an entity that contains itself, otherwise the import is refused with
   `ASSOCIATION_CYCLE`, naming the entities on the cycle. Every entity therefore contains a finite
   tree.
3. **Recursion goes through a reference.** A cycle that includes at least one reference
   association is allowed: "a competency entails competencies" is `Competency` → `Competency` as a
   reference. In the seed, every cycle already passes through a reference.

Both ends are always in the same model, because a reference cannot name another one (§4.3).

The two kinds of association follow [ADR `data_model/0003`](../design/adr/data_model/0003-references-between-shared-entities.md):

- A **contained** child appears in full under its parent.
- A **referenced** child is an entity that exists in its own right; the parent points to it rather
  than containing it. How the generated schema writes the pointer (`$ref` or an explicit reference
  marker) is 0003 Decision 1 (#1026); the file records only `"Reference": true`.

---

## 6. Mapping-group file

### 6.1 Shape

```json
{
  "Format": { "Type": "lif-mdr-mapping-group", "Version": 1 },
  "Details": { … },    // source model, target model, version, and descriptive fields
  "Mappings": [ … ]    // the transformation rules, one per target field
}
```

| `Details` field | Req. | Meaning |
|---|---|---|
| `Source`, `Target` | ✓ | Model identities ([§2](#2-terms)), written inline |
| `Version` | ✓ | Dotted integers such as `1`, `1.0` or `2.10`, as the API already requires (`transformation_group_dto.py`). Stored in the `GroupVersion` column. Together with `Source` and `Target`, the group's key (database unique index `ux_transformationsgroup_model_id_version_active`) |
| `Name` | ✓ | Non-blank display name |
| `Description`, `Notes`, `Contributor`, `ContributorOrganization`, `Tags` | | Descriptive text |

**Activation is local to each install.** A group's `ActivationDate` and `DeprecationDate` decide
whether the Translator uses it (`transformation_service.py`), and #1350 makes an imported group
arrive inactive. The file therefore never carries them: either one in `Details` is refused with
`FIELD_UNKNOWN`. Every other `ActivationDate` and `DeprecationDate` in the format (on mappings,
model elements and crosswalk entries) is carried as stored, because nothing reads them as a
condition: they are descriptive, and can be content a standard publishes, such as a field's
deprecation date. A date that starts controlling behavior on an install moves out of the format in
the same way.

If either model is not installed, the import is refused with `MODEL_MISSING`. If a live group with
the same key exists, it is refused with `GROUP_EXISTS`. Choosing the next version number is endpoint
behavior, not part of the converter.

### 6.2 `Mappings`

| Field | Req. | Meaning |
|---|---|---|
| `Target` | ✓ | `{ "Path": … }` plus optional `Notes`, `Contributor`, `ContributorOrganization` and timestamps. Exactly one |
| `Sources` | ✓ | List of entries shaped like `Target`, sorted by `Path`, with no duplicate paths. May be empty |
| `ExpressionLanguage` | ✓ | Must be `"JSONata"` |
| `Expression` | ✓ | The JSONata expression |
| `Name` | ✓ | Display name |
| `Description`, `UseConsiderations`, `Alignment`, `Notes`, `Contributor`, `ContributorOrganization` | | Descriptive text |
| `ActivationDate`, `DeprecationDate` | | Timestamps |

The rules, from [ADR `metadata_repository/0009`](../design/adr/metadata_repository/0009-mapping-identity-and-cardinality.md):

- **JSONata only.** A rule in any other language is refused with
  `EXPRESSION_LANGUAGE_NOT_PORTABLE`, both when importing a file and when exporting a group. Export
  never quietly drops one.
- **A mapping is identified by `(group, target path)`.** It has exactly one target: a missing
  target is refused with `MAPPING_TARGET_MISSING`, and several with `MAPPING_TARGET_MULTIPLE`. No
  two mappings in a group may write the same target (`MAPPING_TARGET_SHARED`).
- **Sources are content, not identity.** A mapping may declare several sources. The content rules
  (the sources cover every field the expression reads, and the expression writes only its target)
  depend on an expression checker that NEW-I (in the [portability plan](../operations/proposals/mdr-import-export-portability.md)) will define. Until it exists, the converter carries
  the declarations as they are.

### 6.3 Path format

A path names a field: a top-level entity, then association `Name`s, separated by commas.

```
Course,AccreditedBy,name
```

The example is illustrative; a migrated model keeps today's keys, such as
`Course,accreditedByRefOrganization,name`.

1. The first segment is the `UniqueName` of a **top-level entity** (one with no containing parent)
   in the group's source model for a path in `Sources`, or its target model for the `Target` path. In
   the seed, every top-level entity's `UniqueName` equals its `Name` (294 of 294), and all 10 live
   mapping paths start at one.
2. Each later segment is the `Name` of an association under the previous entity, in that model.
   It may cross a reference association.
3. The last segment must reach an attribute.

A path may revisit an entity through a reference: `Competency,Entails,identifier` is valid. Each
path is a finite string, so recursion needs no extra rule.

A path that breaks any of these rules is refused with `PATH_INVALID`, naming the segment. A segment
with a numeric prefix such as `1:` is a legacy model ID and is refused with `ROW_ID_PRESENT`.

Because association names are required (§5.4), a path is never ambiguous:
`Course,AccreditedBy,name` and `Course,ApprovedBy,name` are different fields. Today's
`EntityIdPath` cannot tell them apart. This path format is [ADR `metadata_repository/0010`](../design/adr/metadata_repository/0010-mapping-paths-use-association-names.md), which amends 0009
Decision 1.

---

## 7. Crosswalk file

A crosswalk maps the values of one value set to the values of another, for example Ed-Fi's sex codes
to LIF's. It is the portable form of today's value mappings (`ValueSetValueMapping`).
Implementation belongs to NEW-K (in the [portability plan](../operations/proposals/mdr-import-export-portability.md)).

```json
{
  "Format": { "Type": "lif-mdr-crosswalk", "Version": 1 },
  "Details": {
    "Source": { "Model": { "Name": "Ed-Fi v5", "Version": "1.0", "ContributorOrganization": "LIF" },
                "ValueSet": "SexDescriptor" },
    "Target": { "Model": { "Name": "LIF", "Version": "2.0", "ContributorOrganization": "LIF" },
                "ValueSet": "Sex" }
  },
  "Entries": [
    { "Source": "F", "Target": "Female" },
    { "Source": "M", "Target": "Male" }
  ]
}
```

| Field | Req. | Meaning |
|---|---|---|
| `Details.Source`, `Details.Target` | ✓ | Value-set references, each naming its model by identity, written inline. Either model not installed is refused with `MODEL_MISSING`. Together they form the crosswalk's key; a live crosswalk with the same key is refused with `CROSSWALK_EXISTS` |
| `Entries[].Source`, `Entries[].Target` | ✓ | `ValueName`s in the source and target value sets |
| `Entries[]`: `Description`, `UseConsiderations`, `Notes`, `Contributor`, `ContributorOrganization` | | Descriptive text |
| `Entries[]`: `ActivationDate`, `DeprecationDate` | | Timestamps |

**Each source value maps to exactly one target value.** A second entry for the same source is
refused with `CROSSWALK_SOURCE_DUPLICATE`. Several sources may map to the same target. A source value
with no entry is unmapped.

`Details` holds only the key. Nothing else about a crosswalk as a whole is stored: each value
mapping is its own row, with its own descriptive fields, carried on its entry. `Details` is where
crosswalk-level fields such as a name would go in a later format version.

The seed holds 2,347 live value mappings, but 1,631 of them point at soft-deleted target values
(model 1) and so count as absent (§2). The remaining 716 cover 7 value-set pairs, every source value
set maps to exactly one target value set, and no source value maps to more than one target. Nothing in the runtime reads value mappings today: neither the
Translator nor JSONata does, only the MDR frontend.

---

## 8. The converter

```python
async def export_model(session, data_model_id: int) -> ModelFile
async def import_model(session, file: ModelFile) -> int                  # Id of the new model
async def export_mapping_group(session, group_id: int) -> MappingGroupFile
async def import_mapping_group(session, file: MappingGroupFile) -> int   # Id of the new group
async def export_crosswalk(session, source_value_set_id: int, target_value_set_id: int) -> CrosswalkFile
async def import_crosswalk(session, file: CrosswalkFile) -> int          # number of value mappings created
class PortabilityError(Exception): code, element, reason
```

- **One module covers every file kind, in both directions.** Its intended callers are export,
  import, upload, edit-by-upload (#17), clone and the reference set. Moving the existing
  conversions onto it is later work.
- **Clone is export, then import.** The caller supplies the copy's new identity, and its
  `CopiedFrom` is set to the source's identity. Because every model file is complete, the copy
  stands alone. Clone copies the model only; copying its mapping groups is a separate operation.
- **Single transaction.** The converter never commits; the caller does. Every reference is resolved
  and every rule checked before the first row is written, so a refusal writes nothing.
- **No type names.** There is one kind of model, and no model depends on another.
- **One graph check** (`ASSOCIATION_CYCLE`): from each entity, walk its associations depth-first,
  without following a reference. Reaching an entity that is already on the current path is a
  cycle. Reaching an entity again by a different path is not: a shared entity such as
  `CredentialAward` appears under several parents.
- **Export refuses content that is not yet migrated.** A model whose rows still use a deprecated construct
  (§11) is refused with `NOT_MIGRATED`, naming the construct and the element. That includes today's
  overlay models until they are converted ([ADR `data_model/0004`](../design/adr/data_model/0004-retire-overlays-variants-as-copies.md)). Export never silently turns old content
  into new.

---

## 9. Canonical form

- **Encoding:** UTF-8 JSON, 2-space indent, `\n` line endings, a trailing newline, no byte order mark (BOM).
- **Key order:** the order this spec lists the fields, with `Format` first.
- **Omitted:** optional fields whose value is NULL, and the optional booleans `Reference`,
  `Required` and `Array` when they are not `true`. Required fields are always written, booleans
  included. A file with `"Reference": false` (or `Required` or `Array`) imports correctly but is not
  canonical.
- **Strings** are carried exactly: no trimming, and `""` is not the same as NULL.
- **Timestamps** are RFC 3339 in UTC with `Z`. Fractional seconds are written only when non-zero, up
  to microseconds, with trailing zeros dropped: `2026-02-11T10:04:02.843Z`, and
  `2026-02-11T00:00:00Z` for a whole second.
- **List order:** sorted by key, comparing strings by Unicode code point.

  | List | Sorted by |
  |---|---|
  | `ValueSets` | `Name` |
  | `Values` | `ValueName` |
  | `Entities` | `UniqueName` |
  | `Attributes` | `UniqueName` |
  | `Associations` | `(Parent, Name)` |
  | `Mappings` | target `Path` |
  | `Sources` | `Path` |
  | `Entries` | `Source` |

  A reference sorts as `(element kind, key)`.
- **Creation dates.** `CreationDate` is not part of the format. Import sets it to the import time,
  which is the database default, and a file that carries it is refused with `FIELD_UNKNOWN`. A
  creation date records when a row was written on one install, so carrying it would either be
  ignored on import or make the round trip (§3) depend on it.

---

## 10. Errors

Every error carries its code, the element (by key or path) and a reason. A refused import writes
no rows.

| Code | When |
|---|---|
| `FORMAT_UNKNOWN` | No `Format`, or an unrecognized `Format.Type` |
| `FORMAT_VERSION_UNSUPPORTED` | A `Format.Version` this converter does not read |
| `FIELD_UNKNOWN` | A key the version does not define |
| `DEPRECATED_FIELD` | A key listed in [§11](#11-deprecated); names the key |
| `ROW_ID_PRESENT` | A key named `Id` or ending in `Id` (including `OriginalValueId`), or a path segment with a numeric prefix |
| `MODEL_IDENTITY_INCOMPLETE` | An identity field missing, empty or NULL (seed model 26 has a NULL `ContributorOrganization`; migration sets it to `LIF`) |
| `MODEL_EXISTS`, `GROUP_EXISTS`, `CROSSWALK_EXISTS` | Create-only: the key is already live |
| `MODEL_MISSING` | A model named by a mapping group or crosswalk is not installed |
| `ASSOCIATION_CYCLE` | A cycle of containing associations (§5.4) |
| `REFERENCE_INVALID` | `Reference` on an association whose child is an attribute (§5.4) |
| `REFERENCE_UNRESOLVED` | No live element with that key in the model |
| `DUPLICATE_KEY` | Two entries in one list share a key |
| `ASSOCIATION_NAME_TAKEN` | A parent already has a child under that `Name` |
| `UNASSOCIATED_ATTRIBUTE` | An attribute is in no association |
| `VALUE_NAME_MISSING` | A value without a `ValueName` |
| `EXPRESSION_LANGUAGE_NOT_PORTABLE` | A rule that is not JSONata |
| `MAPPING_TARGET_MISSING`, `MAPPING_TARGET_MULTIPLE`, `MAPPING_TARGET_SHARED` | §6.2 |
| `PATH_INVALID` | §6.3 |
| `CROSSWALK_SOURCE_DUPLICATE` | A source value mapped twice |
| `NOT_MIGRATED` | Export only: the stored rows use a deprecated construct |

---

## 11. Deprecated

These parts of today's MDR are not part of the simplified model. The format cannot express them,
and export refuses content that still uses them (`NOT_MIGRATED`) until it is migrated. Moving
existing content onto the simplified model is migration work, not this spec's.

| Deprecated | Replaced by | Seed content affected |
|---|---|---|
| Model types `BaseLIF`, `OrgLIF`, `PartnerLIF`, `SourceSchema` (`DataModels.Type`) | One kind of model ([ADR `data_model/0004`](../design/adr/data_model/0004-retire-overlays-variants-as-copies.md)) | All 21 models |
| Overlays: a model built on another (`BaseDataModelId`) | A self-contained copy, with `CopiedFrom`. Existing overlays are converted once | 2 models: 17 (StateU LIF, `OrgLIF`) and 18 (Org2 LIF, `PartnerLIF`), both on model 1 |
| Inclusion rows (`ExtInclusionsFromBaseDM`) on a model's **own** elements | Flags on the element itself | 83 live rows whose element is live |
| Inclusion rows (`ExtInclusionsFromBaseDM`) on **another** model's elements | The element, copied into the model | 207 live rows whose element is live, all in models 17 and 18. A further 10 (5 of each kind) name a soft-deleted element and count as absent; 300 live rows in all |
| Constraint and Transformation inclusions | — | 0 rows |
| `ExtendedByDataModelId` on both association tables | Both ends in one model (§5.4): the declaring model is always the owner | 16 + 167 rows |
| Associations between elements of different models | Both ends in one model | 55: 54 involve models 17 or 18, and 1 links model 1 to model 16 |
| Associations where neither end is owned by the declaring model | — | 61 rows. 60 link two elements of one other model (59 in model 16, 1 in model 25) and belong to that model. 1 (`Credential.Image` → OB3's `image.id`) has no owner |
| `Extension` / `ExtensionNotes` (on 8 tables, including `Entities`, `Attributes`, `ValueSets` and `EntityAssociation`) | — | Set only in models 17 and 18: 80 entities and attributes |
| Overrides (an element reusing an inherited `UniqueName`) | — (a model sees only its own elements) | 1 (`Criteria.identifier`, model 17) |
| An attribute using another model's value set | The value set, copied into the model | 1 attribute |
| The `Ref` property keys (`<relationship>Ref<Type>`) | The required association `Name`, plus `"Reference": true`. Retired in a separate step after model 17 is converted; until then a reference association's `Name` keeps the `Ref` spelling (*Migration defaults*) | 24 `Ref` keys in `lif-schema.json`; 21 sample-data, query and config files |
| `Placement` (`Embedded` / `Reference` / NULL) | `"Reference": true` for `Reference`; absent for `Embedded` and NULL. The schema generator already treats NULL as `Embedded`; the Jinja generation code does not (`jinja_helper_service.py`) | 96 `Reference`, 36 `Embedded`, 78 NULL |
| Free-text `Required` and `Array` (`Yes` / `No` / NULL / `""`) on entities and attributes | Booleans: `Yes` becomes `true`; everything else is absent, as the schema generator already reads it (`== "Yes"`). `Required` stays on the element; `Array` moves to every association whose child is that element | Entities: `Required` 7 `Yes`, `Array` 92 `Yes`. Attributes: `Required` 295 `Yes`, `Array` 232 `Yes`. All other values are `No`, NULL or `""` |
| `Relationship` and the `has*`/`relevant*` naming rule | The required association `Name` | 212 entity associations and 2,544 attribute associations need a `Name`; 163 entity associations have no relationship today (115 NULL, 48 empty) |
| Attributes with `DataType = 'entity'` and `TargetEntityId` (`V1.6`) | An association to the entity; an attribute with no target is dropped | 109 attributes. 41 have a target, all in Open Badges v3. 68 have none (CLR v2: 55, CASE: 13) |
| Attributes in no association | Dropped on migration; `UNASSOCIATED_ATTRIBUTE` on import | 99 attributes: CLR v2 48, model 17 14, Open Badges v2 12, Ed-Fi v5 9, EagleApps 7, model 25 4, PESC v1.8 2, LIF 2, OSID / CampusAPI 1 |
| Value mappings' group membership (`TransformationGroupId`), and `SourceValueSetId` / `TargetValueSetId` | The crosswalk file (§7) | 2 rows name a group. The two value-set columns are NULL or disagree with the values' own value sets on 2,345 rows |
| A source value mapped to several targets | `CROSSWALK_SOURCE_DUPLICATE` | 0 among live value mappings. The 8 such values are all on mappings to soft-deleted targets |
| Value mappings to soft-deleted values | — (references to soft-deleted rows count as absent, §2) | 1,631 of 2,347, all targeting model 1 |
| `OriginalValueId`, `OriginalValueMappingId`, `ValueSetValues.DataModelId` | — (the value set's model) | 0 / 0 / always equal to the value set's |
| `DataModelConstraints`, attribute `Constraints`, `ExtMappedValueSet` | — | 0 rows each |
| `InputAttributesCount`, `OutputAttributesCount` | Derivable from the mapping | NULL on all 6 live rules |
| Non-JSONata rules (`LIF_Pseudo_Code`) | `EXPRESSION_LANGUAGE_NOT_PORTABLE` | 1 rule (group 3) |

**Migration defaults.** These rules reproduce the schema MDR generates today, which is ADR
`data_model/0004`'s pass criterion for converting model 17:

- **Flags.** An element with an inclusion row takes its `LevelOfAccess`, `Queryable` and
  `Modifiable` from that row. Every other element gets `Public`, `false` and `false`. Today flags
  are emitted only from inclusion rows, and only for Org LIF and Partner LIF models
  (`schema_generation_service.py`); GraphQL reads a missing `x-queryable` or `x-mutable` as `false`
  (`type_factory.py`).
- **Association `Name`.** For a containing entity association: `Relationship` + the child's
  `Name`, or the bare child `Name` when `Relationship` is NULL, empty, or starts with `has` or
  `relevant`. This is `embedded_property_key` in `schema_generation_service.py`. For a reference association:
  today's key, `<Relationship>Ref<Name>`, or `Ref<Name>` with no relationship, so the 24 published
  `Ref` keys do not change in the same step as the conversion. Retiring them is a separate, later
  step. For an attribute child: the attribute's `Name`.
- **`Array`.** Each association takes its child's current `Array` value.
- **Dropped.** Attributes in no association (99), which do not appear in the generated schema
  today. Entity-typed attributes with no `TargetEntityId` (68), which today appear as attributes of
  type `entity` in CLR v2 and CASE (the generator's `!= "Entity"` check misses the lowercase stored
  value). Dropping them changes those two schemas, not model 17's.
- **Name collisions when flattening an overlay.** Where two elements end up under one parent with
  the same `Name` (in model 17: `id` under `Credential.Image`, from models 16 and 17, and
  `identifier` under `Credential.Requirements.Criteria`, from model 1 and model 17's override),
  the one model 17's generated schema shows today survives. The schema-match check confirms the
  choice.
- **Model 26's organization.** Its NULL `ContributorOrganization` is set to `LIF`. The model keeps
  its ID, so the Query Planner configs that name `source_schema_id: "26"` are unaffected.

**Why the constraint tables were already out.** `ElementType` allows Constraint and Transformation
inclusions, but nothing creates or reads them. `DataModelConstraints` has API endpoints but no UI,
and `ConstraintType` is free text that nothing interprets. Attribute `Constraints` is a model class
with no service. Both constraint tables trace to roadmap items that were never built
([`mdr.md:199-202`](../design/components/mdr.md)). If either is built, a new format version adds it.

---

## 12. Examples

### 12.1 Valid model file: a copy (abridged)

```json
{
  "Format": {
    "Type": "lif-mdr-model",
    "Version": 1
  },
  "Details": {
    "Name": "District LIF",
    "Version": "1.0",
    "ContributorOrganization": "District",
    "CopiedFrom": {
      "Name": "State LIF",
      "Version": "1.0",
      "ContributorOrganization": "State"
    }
  },
  "ValueSets": [
    {
      "Name": "LunchStatus",
      "Values": [
        {
          "ValueName": "Free",
          "Value": "F"
        }
      ]
    }
  ],
  "Entities": [
    {
      "UniqueName": "BusRoute",
      "Name": "BusRoute",
      "LevelOfAccess": "Internal",
      "Queryable": true,
      "Modifiable": false
    },
    {
      "UniqueName": "Student",
      "Name": "Student",
      "LevelOfAccess": "Public",
      "Queryable": true,
      "Modifiable": false
    }
  ],
  "Attributes": [
    {
      "UniqueName": "Student.lunchStatus",
      "Name": "lunchStatus",
      "DataType": "string",
      "ValueSet": {
        "ValueSet": "LunchStatus"
      },
      "LevelOfAccess": "Restricted",
      "Queryable": true,
      "Modifiable": true
    },
    {
      "UniqueName": "Student.ssn",
      "Name": "ssn",
      "DataType": "string",
      "LevelOfAccess": "Private",
      "Queryable": false,
      "Modifiable": false
    }
  ],
  "Associations": [
    {
      "Parent": {
        "Entity": "Student"
      },
      "Child": {
        "Entity": "BusRoute"
      },
      "Name": "BusRoute"
    },
    {
      "Parent": {
        "Entity": "Student"
      },
      "Child": {
        "Attribute": "Student.lunchStatus"
      },
      "Name": "lunchStatus"
    },
    {
      "Parent": {
        "Entity": "Student"
      },
      "Child": {
        "Attribute": "Student.ssn"
      },
      "Name": "ssn"
    }
  ]
}
```

### 12.2 Valid mapping-group file

```json
{
  "Format": {
    "Type": "lif-mdr-mapping-group",
    "Version": 1
  },
  "Details": {
    "Source": {
      "Name": "Ed-Fi v5",
      "Version": "1.0",
      "ContributorOrganization": "LIF"
    },
    "Target": {
      "Name": "StateU LIF",
      "Version": "1.0",
      "ContributorOrganization": "StateU"
    },
    "Version": "1.0",
    "Name": "Ed-Fi v5_StateU LIF"
  },
  "Mappings": [
    {
      "Target": {
        "Path": "Assessment,identifier"
      },
      "Sources": [
        {
          "Path": "Assessment,AssessmentIdentifier"
        }
      ],
      "ExpressionLanguage": "JSONata",
      "Expression": "{ \"Assessment\": Assessment. { \"identifier\": AssessmentIdentifier } }",
      "Name": "Assessment.identifier"
    }
  ]
}
```

### 12.3 Invalid

| Fragment | Error |
|---|---|
| `{ "Id": 133, "UniqueName": "Assessment", … }` in `Entities` | `ROW_ID_PRESENT` (`Entities[Assessment].Id`) |
| `"Reference": true` on an association whose child is an attribute | `REFERENCE_INVALID` |
| `"Placement": "Reference"` on an association | `DEPRECATED_FIELD` (`Placement`) |
| `"Type": "OrgLIF"` in a model file's `Details` | `DEPRECATED_FIELD` (`Type`) |
| `"ActivationDate": "2026-10-06T00:00:00Z"` in a mapping-group file's `Details` | `FIELD_UNKNOWN` (`ActivationDate`) |
| `"CreationDate": "2026-10-06T00:00:00Z"` on any object | `FIELD_UNKNOWN` (`CreationDate`) |
| `"Includes": [ … ]` at the top level | `FIELD_UNKNOWN` (`Includes`) |
| `{ "Model": "State LIF", "Entity": "Student" }` as an association end | `FIELD_UNKNOWN` (`Model`) |
| `Student` → `Student` without `Reference` | `ASSOCIATION_CYCLE` (`Student`) |
| Two associations under `Course` named `AccreditedBy` | `ASSOCIATION_NAME_TAKEN` (`Course`, `AccreditedBy`) |
| Two entities with `UniqueName` `Student` | `DUPLICATE_KEY` (`Student`) |
| `"ExpressionLanguage": "LIF_Pseudo_Code"` | `EXPRESSION_LANGUAGE_NOT_PORTABLE` (the mapping's target path) |
| Two mappings with target `Assessment,identifier` | `MAPPING_TARGET_SHARED` |
| `"Path": "1:Assessment,1:~Assessment.identifier"` | `ROW_ID_PRESENT` (segment `1:Assessment`) |
| A crosswalk with two entries for source `F` | `CROSSWALK_SOURCE_DUPLICATE` (`F`) |
| `"Format": { "Type": "lif-mdr-model", "Version": 2 }` | `FORMAT_VERSION_UNSUPPORTED` |

---

## 13. Open questions

| # | Question | Draft position |
|---|---|---|
| **Q1** | Are recursive associations allowed? | Yes, through a reference (§5.4), per [ADR `data_model/0003`](../design/adr/data_model/0003-references-between-shared-entities.md). Containing associations stay acyclic, so records stay finite. All 13 entities on cycles in the seed are on cycles only through reference associations |
| **Q2** | Should association `Name` be required on every association, including attributes? | Required, for one consistent rule. It repeats the attribute's `Name` on every attribute association |
| **Q3** | Should mapping paths use association names (§6.3) instead of `EntityIdPath` `UniqueName`s? | Yes, because `UniqueName` paths cannot distinguish roles. Decided in [ADR `metadata_repository/0010`](../design/adr/metadata_repository/0010-mapping-paths-use-association-names.md), which amends 0009 Decision 1 |
| **Q4** | Is turning entity-typed attributes (`TargetEntityId`) into associations acceptable? | Yes. They are references by another name |
| **Q5** | Which ADRs change? | `data_model/0002` is already superseded by `data_model/0004`, which this spec follows. `data_model/0003` is unchanged: the spec keeps its distinction between containing and referencing. `metadata_repository/0009` Decision 1 is amended by `metadata_repository/0010` (Q3) |
| **Q6** | Should a path through a reference reach any attribute of the referenced entity, or only its key and attested fields (0003 Decision 4)? An **attested field** is a detail that was part of what a record certified when it was issued, such as the issuer's name as printed on an award. 0003 copies attested fields onto the reference, because the referenced entity may change later (an institution is renamed) while the record must keep what it stated | Any attribute, for now. 0003 Decision 4 has no model-level marker for attested fields yet. Today `Required` stands in for one: a referenced entity's schema keeps only its `Required` attributes (`add_ref` in `schema_generation_service.py`; ADR `metadata_repository/0008`), so `Required` means both "must be present" and "shown in references" |
| **Q7** | Should `Array` (cardinality) move from the element to the association? | Yes, adopted in §5.4. `Array` belonged to the element, so a shared entity had one cardinality under every parent: `CredentialAward` has seven parents and one `Array` value. On the association, each parent could choose. This changes the model, not just the file |

**What this needs from the database.** The format is the contract, but importing it needs
storage changes that do not exist yet:

- flags on `Entities` and `Attributes`;
- a `Name` and `Array` on both association tables;
- a lineage (`CopiedFrom`) column on `DataModels`, applied to every tenant schema, not only
  `public` (#1226);
- today's overlay models converted into self-contained models, after which inclusion rows are no
  longer used;
- the deprecated columns ignored, and later dropped.

Those changes are Flyway migrations, and the schema generator has to change with them. They are
separate work, and they come before the converter can write rows.
