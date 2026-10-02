# MDR import/export portability (schemas + mappings)

**Status:** Proposed
**Date:** 2026-09-25
**Author:** cbeach47
**Tracking issue:** [#1223](https://github.com/LIF-Initiative/lif-core/issues/1223) (epic)

Plan to make MDR schemas and mappings portable between installs: name-based import/export, no database IDs in files, edit-by-upload.

A data model and its mappings should export from one MDR install and import into another that
shares no database — references intact, no database IDs in the file — and the same file should be
usable to **edit** what is already there, not only to create something new.

Throughout, two terms do a lot of work:

- **Portable file** — the JSON a user exports and re-imports. Portable means no reference in it is
  a database row ID, because row IDs mean nothing in another install. Most things are identified by
  name; mappings have no usable name, so they are identified by the target field they write
  (Decision 3).
- **Anchor** — the data model an import is aimed at, named by the request (a URL or form field),
  never read from the file.

> **How to read this.** Every claim was checked against `main` @ `b97cd63`. Where a measurement
> contradicted an assumption, the losing reasoning is kept so it is not re-argued later.
>
> **Do not infer structure from the seed data.** Twice during this review the shipped data implied
> a limit the code does not enforce (Gap E). Check the model definition, the database constraints
> and the calling code — not what today's 21 models happen to look like.

---

## Goals

1. **Portability** — import files must not rely on database IDs.
2. **Data out of migrations** — migrations hold schema definitions only; a reference set of JSON
   files reproduces what ships with MDR. *(Deferred — see Decision 2.)*
3. **Edit by file import** for any schema or mapping, not just create.
4. **Automated tests import JSON files**, MDR-only, not the full-stack integration suite.

Export and import are the two workhorses of this flow, so both get reworked as a matter of course
rather than as a separate goal.

Two hazards flagged at kickoff, both confirmed real. The second is the four model types, which do
not share a code path. The first is how references are stored — and there are more kinds than
"embedded vs referenced":

| Kind | Stored as | Live rows |
|---|---|---|
| Entity nested inside a parent | `EntityAssociation.Placement = Embedded` — or **NULL**, which the generator treats as embedded | 37 + 78 NULL |
| Entity pointed at from another entity | `EntityAssociation.Placement = Reference` | 97 |
| **Attribute pointing at an entity** | `Attribute.DataType = 'entity'` plus `Attribute.TargetEntityId` | 109 entity-typed attributes |
| Attribute pointing at a value set | `Attribute.ValueSetId` | 2,285 |
| Entity ↔ attribute membership | `EntityAttributeAssociation` (many-to-many) | 2,544 |
| **Link added by an extension** | `ExtendedByDataModelId` on `EntityAssociation` / `EntityAttributeAssociation` — the extension adds a link between elements it does not own | 16 + 167 |
| **Element exposed by an extension** | `ExtInclusionsFromBaseDM` row carrying `LevelOfAccess` / `Queryable` / `Modifiable` | 300 |

The third row is the newest and the least handled. `TargetEntityId` was added in `V1.6` precisely
because `DataType = 'entity'` said an attribute referred to *some* entity without saying which; the
migration comment is explicit that the exporter neither records nor infers the binding, and warns
against guessing it from names. The column is a raw row ID, it already sits on the attribute record
that export serializes, and **nothing in the import path handles it** — so today it either leaks a
meaningless ID into the file or is dropped. Phase 1 has to give it a name-based form like any other
reference.

---

## What is broken today

### Three export failures, all live

| Request | Failure | Where |
|---|---|---|
| `GET /import_export/export/{id}` | `check_base=False` passed to two functions that don't accept it → `TypeError` | [`import_export_service.py:118`](../../../components/lif/mdr_services/import_export_service.py#L118), [`:142`](../../../components/lif/mdr_services/import_export_service.py#L142) |
| `GET /import_export/export/multiple/` | unpacks **6** of the **7** values it is given, then builds a record missing a required field | [`import_export_service.py:166-176`](../../../components/lif/mdr_services/import_export_service.py#L166-L176) |
| `GET /import_export/export/{id}` for a **PartnerLIF** | the base-model lookup filters on `Type == "OrgLIF"`, so a PartnerLIF finds nothing and the result is used anyway → `AttributeError` | [`datamodel_service.py:413-421`](../../../components/lif/mdr_services/datamodel_service.py#L413-L421) |

The first two are **#1210** and **#1211** (each an export endpoint returning 500); PR #1212 fixes
#1210. The third was untracked when this plan was written and is now **#1321**, filed ahead of the
other proposed tickets because it is currently hidden behind #1210 — which fails first, so PR #1212
exposes it on merge. Seed model 18 (`Org2 LIF`) triggers it, and #1321 adds a second entry point
this table missed: `GET /datamodels/base/{id}` hits the same lookup with no type guard at all, so
it 500s for a PartnerLIF id and for any id that does not exist, where a 404 is correct. None of the
three has a regression test, and the two originally tracked were reported by an outside contributor
rather than caught in CI.

### Database IDs in import files — one bug, four times

On create-by-upload, the **OrgLIF / PartnerLIF** path looks up existing rows using the ID written
in the uploaded file. The SourceSchema path already looks them up by name.

| Ticket (each: "search portably for X on upload") | Where | The lookup |
|---|---|---|
| **#762** attributes | [`schema_upload_service.py:286`](../../../components/lif/mdr_services/schema_upload_service.py#L286) | `session.get(Attribute, attribute_md.get("Id"))` |
| **#763** value sets | [`:396`](../../../components/lif/mdr_services/schema_upload_service.py#L396) | `session.get(ValueSet, ...get("Id"))` |
| **#764** values | [`:258`](../../../components/lif/mdr_services/schema_upload_service.py#L258) | `session.get(ValueSetValue, value.get("Id"))` |
| **#765** entities | [`:458`](../../../components/lif/mdr_services/schema_upload_service.py#L458) | `session.get(Entity, entity_md.get("Id"))` |

This is the model-type hazard exactly: the defect exists *only* on the two extended types. Each
ticket already prescribes the right fix — drop the type check, search by name within the model.

### Export and import speak different languages

Export writes records keyed by database ID. Import reads records keyed by name
([`import_export_dto.py`](../../../components/lif/mdr_dto/import_export_dto.py)). The two shapes
have never met, so the documented round trip has never worked. That is **#1008** (add a name-based
export so export output can be fed back into import).

The import record also has mappings and entity-attribute links **commented out**, with a note that
same-named attributes make them ambiguous. That is a real problem the file format has to answer,
not an oversight.

### How much content is actually in the box

Active (not soft-deleted) rows in `V1.1__metadata_repository_init.sql`:

```
DataModels 21  (18 SourceSchema, 1 BaseLIF, 1 OrgLIF, 1 PartnerLIF)
Entities  397   Attributes 2285   ValueSets 235   Values 3765
Associations 212 + 2544   Inclusions 300   ValueMappings 2347
Mappings: 9 groups, 6 transformations, 10 transformation attributes
```

All four model types are present, so the test matrix has real fixtures without inventing any. And
**mappings are tiny** — the file carries 1,378 mapping rows but only 6 are live; the rest are
soft-deleted. Mapping work is much smaller than the raw row counts suggest.

---

## Gaps no ticket covers

### A. Export silently drops two tables, and they are not the same problem

Base-model inclusions (300 live rows) and value mappings (2,347) appear **nowhere** in
`import_export_service.py` — not in export, and not in `clone_datamodel` either. The epic treats
`clone_datamodel` as the reference implementation for ID remapping. **It is not a sound one** —
measured against a live database, not just read:

- `clone_transformations` returns from inside its loop over groups
  ([`import_export_service.py:664`](../../../components/lif/mdr_services/import_export_service.py#L664)),
  so only the first group's rules are cloned. Cloning model 17 copied 6 groups and **0 of their 5
  live rules**, because the first group happened to be empty.
- `clone_transformation_attributes` never sets `TransformationAttribute.EntityId`, which is
  `NOT NULL` — any clone that does reach a rule's attributes fails on insert.
- It drops `Relationship`, `Placement` and `ExtendedByDataModelId` from entity associations,
  `ExtendedByDataModelId` from entity-attribute links, `TargetEntityId` from attributes, and
  `ContributorOrganization` (declared required) from the model.

Treat it as a checklist of what a copy must cover, not as code to imitate. Once the converter
exists, clone becomes export-then-import through it.

An exported OrgLIF or PartnerLIF therefore loses its entire inclusion set — the thing that makes it
an extension (206 rows for model 17, 94 for model 18). Biggest correctness hole in the schema half.

**Inclusions are not only "from the base".** Despite the table name, an inclusion row is the
visibility record for *every* element an extended model exposes, and it carries `LevelOfAccess`,
`Queryable` and `Modifiable`. The schema generator returns 404 when one is missing
([`schema_generation_service.py:146-164`](../../../components/lif/mdr_services/schema_generation_service.py#L146-L164)).
Of the 300 live rows:

| Inclusion points at | Model 17 | Model 18 |
|---|---|---|
| The parent (model 1) | 138 | 49 |
| The model's own elements | 67 | 21 |
| A model outside the ancestor chain | 1 (model 16) | 24 (22 in model 17, 2 in model 25) |

So the file must carry inclusion flags on owned elements too, and 25 rows reference a model that
is neither the anchor nor an ancestor — the same peer-model problem value mappings have (below).
Whether an extension may include a *sibling's* elements (18 including 17's) is a product question
the format has to answer, not infer.

**Attribute-level `Constraints`** (a separate table from `DataModelConstraints`) are handled by none
of the conversions. That is not a gap: the table has no service, endpoint or UI and 0 rows, and
the format deliberately does not carry it (Phase 1, "Which kinds of element the format carries").

**But the two tables need different fixes.** Inclusions mostly fit the anchor-plus-ancestors rule
(most rows point at model 1, the parent, or at the model itself). Value mappings do not. Measured on
active rows: **all 2,347 are cross-model, none are same-model.** Sources are ten SourceSchemas
(2, 3, 4, 7, 9, 10, 12, 14, 15, 25); targets are BaseLIF model 1 and PartnerLIF model 18. A
SourceSchema has no parent and appears in nobody's ancestor chain, so a value mapping's source end
is **neither the anchor nor an ancestor**.

That needs a third kind of reference in the file format — a **peer-model reference**, resolved by
the three-field model identity — and it behaves like the mapping half of the epic, not the schema
half. So inclusions and value mappings get separate tickets in separate phases.

Value mappings are also **not really grouped**: only 2 of the 2,347 set `TransformationGroupId`
(and one of those two points at a deleted group). They are value-set-to-value-set links, so which
file carries them — the schema file, the mapping file, or a file of their own — is for NEW-K to
settle.

### B. There is no update path for schemas

`import_datamodel` only ever creates
([`import_export_service.py:196`](../../../components/lif/mdr_services/import_export_service.py#L196)).
Goal 3 has no backing code at all. **#17** (backend: update a schema by upload) and **#18**
(frontend button for it) describe the flow but predate this work.

### C. Seven of nine mapping groups cannot be exported — and mostly they should not

[`transformation_endpoint.py:234-246`](../../../bases/lif/mdr_restapi/transformation_endpoint.py#L234-L246)
exports only JSONata rules. A group with none returns **400 — "There are no valid transformations
to export for this group / version. Please add a transformation to this group's version and retry
the export."** Only groups 25 and 26 export today.

Measured on active rows, the seven split into two groups that have nothing to do with each other:

- **Six are simply empty** — 12, 15, 16, 22, 23 and 24 have no live rules at all, and return the
  same 400 from the `total_count == 0` check whether the filter exists or not. Getting them to
  export means *putting mappings in them* — authoring content, not fixing code.
- **One, group 3, is filtered out** — its single rule is written in `LIF_Pseudo_Code`.

**The filter is correct.** Non-JSONata rules are not supported transformations; `LIF_Pseudo_Code`
is the column default, so it is what a rule gets when nobody picked a language, which makes those
rows drafts rather than executable mappings (Decision 4). Group 3 should not export, and removing
the filter would produce a file that cannot be executed on the other side.

**The defect is the error message, not the filter.** All three cases — empty group, non-JSONata
rules, some of each — return one 400 that says "add a transformation and retry", which is wrong
advice for a group that already has one. It should name the real reason: this group's rules are
not JSONata, and only JSONata is portable.

So the exportable count stays at 2 out of 9, and that is the correct number. What changes is that
a user is told why.

> *Superseded theory, kept so it is not retried:* export looked like it should crash on a null
> path (2,693 of 2,746 rows have one). It does not — those rows are soft-deleted and never reach
> the code. The JSONata filter is the real blocker. The null-path fragility is real but latent.

### D. Two seed files, kept in sync by hand

`V1.1__metadata_repository_init.sql` (19,911 lines, main schema) and
[`backup.sql`](../../../projects/lif_mdr_database/backup.sql) (38,702 lines, main **+** tenant
schema). Both carry the same seed content; the test harness loads the **second**
([`conftest.py`](../../../test/bases/lif/mdr_restapi/conftest.py)). Anything done to one must be
done to the other.

### E. A model's parent chain has no depth limit, and almost nothing follows it

An OrgLIF or PartnerLIF extends a parent model. Following each parent to the root gives the
**ancestor chain** — and resolving a name means searching the anchor plus every ancestor, with the
nearest winning.

`BaseDataModelId` is a plain self-reference with **no constraint on type or depth**
([`mdr_sql_model.py:81`](../../../components/lif/datatypes/mdr_sql_model.py#L81)). Creation requires
an OrgLIF/PartnerLIF to *have* a parent but never checks what kind
([`datamodel_service.py:234-238`](../../../components/lif/mdr_services/datamodel_service.py#L234-L238)),
and the UI takes the parent as a free-typed number.

So **OrgLIF → PartnerLIF → BaseLIF is permitted and creatable** — and nothing caps it there. The chain can be arbitrarily long, and with no cycle guard
it can also be circular. Treat depth as unbounded. One function already walks it to the root:
`get_base_model_ids` — a loop that would be pointless at depth one.

It exists in **two copies that are not identical, and the uncalled one is the broken one**:

- [`jinja_helper_service.py:578`](../../../components/lif/mdr_services/jinja_helper_service.py#L578)
  tests truthiness (`while current_model_id:`), so a model with ID 0 ends the walk early.
  **No callers.**
- [`jinja_translation_service.py:716`](../../../components/lif/mdr_services/jinja_translation_service.py#L716)
  tests `is not None`, carries a comment explaining that fix, and has regression tests asserting
  `[7, 0, 2]`. **This is the one in use** (called at `:875-876`).

Keep the second. Neither has a cycle guard, and Gap E's own argument — an unconstrained
self-reference, no type check, a free-typed number in the UI — means a model can be made its own
ancestor, which would hang the walk.

Everything else assumes a single parent: the two name-lookup helpers search exactly two models, and
so do `valueset_service.py:216,250` and `transformation_service.py:1595,1603`.

Three consequences:

1. **The export record bundles the parent, and should not** — it has exactly two slots,
   `BaseDataModel` and `ExtendedDataModel`
   ([`import_export_dto.py:41-43`](../../../components/lif/mdr_dto/import_export_dto.py#L41-L43)),
   so a three-deep model has nowhere to put its grandparent. The fix is to drop the bundle, not to
   widen it — see below.
2. **Exporting any PartnerLIF fails** — the third row in the table above. Now filed as
   **#1321**, which found a second entry point for the same bug: `GET /datamodels/base/{id}`
   500s for any id that is not a live OrgLIF, where a 404 is the right answer.
3. **Name lookups must search the whole chain**, which is what `get_base_model_ids` already does
   and no import/export code calls.

None of the 21 seed models is three deep, which is why this stayed invisible — and why the test
matrix needs a three-deep fixture.

**One file per model, imported in order — drop the parent slot.** Raised in review: if A is the
parent of B and B of C, why not export `a.json`, `b.json` and `c.json` and import them in that
order? That is right, and the bundled parent slot turns out to be dead weight already:

- **Import never reads it.** `POST /import/` takes `ImportDataModelDTO`, a different shape
  entirely — the two-slot `DataModelExportDTO` is an export-only structure, so the bundled parent
  is written and never consumed.
- **The resolution rule says the same thing.** Ancestors resolve from the *target database's* own
  parent chain, never from the file. A copy of the parent in the file has no one to talk to.
- **A flat export already exists.** `GET /export/multiple/` returns
  `List[SingleDataModelExportDTO]` — no parent slot, no nesting.
- **The slot is the sole cause of #1321.** `get_base_model_for_given_orglif` exists only to fill
  it, and that lookup is what 500s on a PartnerLIF.

So the export record does not need an ancestor list. Each model exports standalone and names the
parent it extends by the three-field model identity (name, version, organization); import resolves
that name against what is already installed and refuses if the parent is missing. Depth stops
mattering — a chain of any length is just N files imported parent-first — and a whole category of
bundling bugs disappears with the slot. Ordering the files is the importer's job under **#1333**, and
`/export/multiple/` is the shape to build on.

### F. Targets are unowned, and export keeps only the last one it sees

Two separate problems sit on the target side, and Decision 3 depends on telling them apart.

**Export drops all but one target of a mapping.** `transformation_service.py:1195` assigns the
target by plain overwrite while looping over a mapping's attribute rows, so a mapping that writes
two fields exports as if it wrote one. Nothing stops it having two: there is no uniqueness rule on
mapping attributes, and an `OutputAttributesCount` column exists. Under Decision 4 this is
straightforward data loss and export has to carry the full set.

**Nothing says a target field belongs to one mapping.** Two mappings in the same group can both
write `Person.Name.firstName`, and today nothing rejects that — on export one wins by row order,
and which one is arbitrary. This is the one Decision 3 turns into a rule: **within a group, each
target field is written by exactly one mapping.** A source may feed many targets — that fan-out is
normal, and 15 source paths in the reference transforms already do it — but a mapping records a
single source, so many-to-one is not a declarable shape (Decision 3).

Of the six live mappings in the database, five have exactly one target and one (transformation
1189, group 3) has none — a sample too small to conclude anything from, which is why the rule was
measured against the 185 mappings in the reference transforms instead (Decision 3).

---

## Tickets already satisfied

| Ticket | Evidence | Action |
|---|---|---|
| **#1252** — export 500 on a nested embedded parent | Fixed and **already closed** on GitHub; the two functions now agree on naming ([`schema_generation_service.py:355-400`](../../../components/lif/mdr_services/schema_generation_service.py#L355-L400)). | **None — listed so it is not re-opened** |
| **#717** — fetch the schema from MDR instead of a file | Done. Services load from MDR at startup, with a documented dev-only file fallback. | **Close as stale** |
| **#746** — enforce unique names on anything exportable | Mostly done in the database: 8 uniqueness rules already cover models, entities, attributes, value sets, values, mapping groups and both link tables. | **Re-scope** to the one gap: mapping names |
| **#1063** — round-trip test matrix | The "fail loud, not skip" bullet *happens* to hold — CI run `35801872026` ran the round-trip test against real Postgres, 861 passed, zero skipped — but nothing guarantees it. | **Keep all bullets**; re-scope that one to "fail, don't skip" (below) |

The last one matters twice over.

**The database-backed test harness goal 4 needs already exists and already runs in CI.** The
JSON-import suite extends `conftest.py` rather than building anything new.

**But it runs there by accident, so #1063's bullet stays.** The fixture calls `pytest.skip` when
it cannot start a server ([`conftest.py:34-37`](../../../test/bases/lif/mdr_restapi/conftest.py#L34-L37)):

```python
try:
    postgresql = testing.postgresql.Postgresql()
except RuntimeError as e:
    pytest.skip(f"PostgreSQL not available locally: {e}")
```

`pr-ci.yml` runs on `ubuntu-latest` and has no `postgres` service and no install step — a
repo-wide search for `postgres` across `.github/workflows/` returns nothing. The round-trip test
gets a database purely because the runner image ships with PostgreSQL. If that changes, every
one of these tests turns green by skipping and the portability guarantee goes silently unproven,
which is exactly the failure the bullet was written about.

So re-scope rather than drop: **skip locally, fail when `CI` is set.** Gate the `pytest.skip` on
`os.environ.get("CI")` and raise instead when it is, so a missing database is a red build and not
a quiet pass. Cheap, and it makes the "already true" claim above actually enforced.

---

## Decisions

Five decisions, all made here. Each one below states the options that were weighed, the evidence,
and the call. They shape three tickets — NEW-J (D1), NEW-I (D3) and NEW-F (D5) — so they need to
hold before those get estimated.

| # | Question | Decision |
|---|---|---|
| **1** | What does an import do to content the file omits? | **1a** — mirror, with a preflight preview |
| **2** | Does this epic pull seed data out of the migrations? | **No** — prove the round trip, defer the slimming |
| **3** | What identifies a mapping across installs? | **3b** — `(group, target path)` |
| **4** | Must a round trip be lossless? | **Yes**, for JSONata expressions |
| **5** | How far does the ancestor chain investment go? | **5a** — one helper, full chain everywhere |

---

### 1. What does an import do to content the file omits?

**Decision: 1a — the file is authoritative, with a preflight preview and a confirm step.**

#17 already specifies that an upload removes anything absent from the file. That makes "uploading
the wrong file" a mass delete: every name misses, so everything present is removed. The options:

| Option | Behavior | Cost |
|---|---|---|
| **1a — Mirror, with preflight** ✅ | File is authoritative; absent means delete. A **preflight preview** shows what would be created, updated and **deleted**, and the user confirms. | NEW-J, plus the confirm step in the UI |
| **1b — Additive only** | Import creates and updates, never deletes. Deletion stays an explicit UI action. | Cheapest; but "edit by upload" can no longer remove a field, so a round trip is not a true mirror |
| **1c — Per-import mode** | The request says `merge` or `replace`. | Both paths to build and test; two behaviors to document |

**Why 1a.** Goal 3 is edit-by-upload, and 1b cannot do it — a file that can add a field but never
remove one is not an editing interface, it is an append interface, and the round-trip proof in
Phase 6 would not be comparing like with like. 1c buys back that ability at the price of two
behaviors to build, test and explain, and the merge half would still be the unsafe one when
someone picks it by mistake. The danger in 1a is not deletion itself, it is deletion nobody
looked at — so the preview is the mitigation, and it is worth building once for the one path that needs it.

**Two constraints that hold regardless.** Deletion is limited to the anchor — an element that
resolved from an *ancestor* is never deleted by an edit to the child model. And the hazard noted
above is real until export is complete: a round-trip edit of an OrgLIF today would delete its
entire inclusion set (206 rows for model 17, 94 for model 18), which is why delete-on-import must
not ship before export emits every element kind.

**The preview has to cross into mappings.** A schema upload can break mappings that the file
never mentions, because a mapping binds to schema elements **by row ID**:
`TransformationAttributes.AttributeId` and `.EntityId` are foreign keys into `Attributes` and
`Entities` ([`mdr_sql_model.py:350-366`](../../../components/lif/datatypes/mdr_sql_model.py#L350-L366)).
Two ways an edit-by-upload damages them:

- **Removing an attribute that a mapping uses.** Under 1a, an attribute absent from the file is
  deleted — and `delete_attribute` is a hard `session.delete`, which clears
  `EntityAttributeAssociation` rows but not `TransformationAttributes`
  ([`attribute_service.py:214-239`](../../../components/lif/mdr_services/attribute_service.py#L214-L239)).
  So the delete hits the foreign key and surfaces as a **500 carrying a raw database error**. With
  per-row commits (NEW-H) that can also leave the model half-imported.
- **Renaming a target attribute.** The foreign key still resolves, so nothing errors — but the
  mapping's identity under Decision 3 has changed, and the denormalized `EntityIdPath` string on
  the mapping row still spells the old name. The breakage is silent.

**The preflight must report mapping impact, and the import must not proceed unnoticed.**
The rule: an import that would delete or rename schema elements which mappings depend on lists
those mappings, with counts, and requires explicit confirmation; if a mapping would be left
referencing something that no longer exists, it is **blocked**, not warned. That is a cheap
addition to NEW-J — it is the same diff the preview already computes, followed one foreign key
further — and without it "edit by upload" can quietly break transformation logic that the uploaded
file says nothing about. This is also why NEW-H (import in a single transaction) is not optional:
the preview's promise is only as good as the ability to roll the whole thing back.

**Either way:** #768 (accept a default model ID and an ID map on upload) and #775 (list the model
IDs found in an upload) close. Both exist only to cope with IDs in files; the anchor comes from the
request and the upload endpoint already takes the parent model as a form field. NEW-J replaces
them.

---

### 2. Keep the round-trip proof; defer the migration slimming — *settled (scope)*

`backup.sql` should track the latest migration. Actually pulling seed data out of the migrations is
a **separate effort** after portability lands. This epic still proves the end state — export the
shipped content, import it into an empty install, assert the result matches — without removing
anything from the migrations. Same guarantee, no migration surgery, and the follow-on effort
inherits a working extractor.

---

### 3. What identifies a mapping across installs?

**Decision: 3b — a mapping is identified by its target, as `(group, target path)`.**

Entities, attributes and value sets already have a portable identity in their unique name.
Mappings are the outlier — which is what #1140 ran into.

**The name cannot do it.** Nothing enforces mapping-name uniqueness — that absence
is exactly the #746 remainder — and names are editable, so a name is not an identity. (The seed
data does hold 118 duplicate (group, name) pairs, but every one is soft-deleted version history;
on active rows there are zero, so do not lean on that figure.)

| Option | Identity | Schema change |
|---|---|---|
| **3a — Generated `PortableKey`** | A random UUID on each mapping, written into exports and **preserved on import rather than regenerated** | New column + backfill migration |
| **3b — `(group, target path)`** ✅ | The target field names the mapping; sources and expression are content | None — but needs a uniqueness rule |

**3a in detail.** Generate the UUID in **Python at creation**, not SQL — the key must be preserved
on import, so application code owns it either way, and a SQL default invites someone to regenerate
it. Unique **per group**, so cloning a group into a new version can keep keys and let you diff
versions. Backfill with `WHERE "PortableKey" IS NULL` so the migration replays safely. Where no key
is present (hand-written files, older exports), fall back to target plus sorted sources — as a
readable tuple, not a hash. It stays stable through any edit to paths or expressions, which a
content-derived hash would not.

**3b in detail** (raised in review, and the option chosen). Identity is `(group, target path)`,
resting on one rule: **within a group, no two mappings write the same target field.** That keeps
identity stable through source and expression edits — the same requirement 3a is built for — with
no generated key and no migration. Where a value needs a fallback, the JSONata expression handles
it with `??`, `?:` and `$exists()` — the expression is free to read what it likes; it is the
recorded source *binding* that stays single.

**"Group" here means the group's portable identity, not its name.** The database's only rule on
groups is `ux_transformationsgroup_model_id_version_active` on `(GroupVersion, SourceDataModelId,
TargetDataModelId)` — `Name` is not in it. Across installs a group is therefore identified by
(source model identity, target model identity, `GroupVersion`), each model identity being the
three-field `(Name, DataModelVersion, ContributorOrganization)`.

**What the rule does and does not constrain.** It constrains *targets*, not sources:

- **One source → many targets is fine.** The same source path may feed any number of target
  fields; each is its own mapping with its own target, so each has its own identity. Fan-out is
  normal and stays supported.
- **Many sources → one target is not supported.** A mapping records **one** source attribute. The
  JSONata expression may of course navigate and read whatever it needs, but the recorded source
  binding is single — so "combine five attributes into one field" is not a shape a mapping can
  declare.
- **A mapping that writes several targets is fine.** Its identity is then its *set* of targets —
  and because no target is written twice in a group, that set is unique, so any member of it finds
  the mapping. Export has to carry all of them, which is the first half of Gap F.
- **Two mappings writing the same target in one group is rejected.** It was already broken, just
  silently (see Gap F).

**The data says the same thing.** Of the 183 well-formed mappings, **179 record exactly one
source.** All four exceptions are unfinished drafts, and in every one the expression reads only a
single source anyway — the extra bindings are annotations nobody wired up:

| Mapping | Sources recorded | What the expression actually reads |
|---|---|---|
| 1634 `StudentEducationOrganizationAssociation.Race` | 5 race attributes | `Culture.americanIndianOrAlaskan` only |
| 1636 `{Multiple}.Sex` | `sex`, `gender` | `SexAndGender.sex` only |
| 1653 `Address.Period` | `dateEffective`, `dateExpired` | `dateEffective` only |
| 1578 `achievement.name / description` | `name`, `description` | `name` only |

Two of those four write to placeholder targets (`{Multiple}`, `name / description`) that are not
real fields. So many-to-one is not an established pattern the rule would break — it is a way of
leaving a note on a half-written rule, and a single-source binding makes that impossible to
confuse with a finished mapping.

**The cost of 3b: renaming a target field.** A rename does **not** require a new schema version —
a target field can be renamed in place. When that happens the mapping's identity changes with it,
so an import sees the old target gone and a new one arrived, and processes it as a delete plus a
create rather than an edit. Anything held on the row and not in the file — notes, contributor,
dates — does not survive that.

This is the real price of 3b and it is accepted rather than argued away. Two things keep it small:
renaming a target field is rare and deliberate, and under Decision 1 the preflight preview shows
it as an explicit delete-and-create before anything is written, so it is visible rather than
silent. A generated key (3a) would have survived it in place — that is 3a's one genuine advantage,
and it costs a column, a migration and a backfill to buy.

**Measured, because the rule is only as good as the data.** Across the three versioned transforms
in [`reference_data/transformations/`](../../../reference_data/transformations/) — 185 mappings in
groups 29, 49 and 50 — every well-formed mapping already satisfies it:

| Group | Mappings | Distinct target paths | Duplicates |
|---|---|---|---|
| 29 (`Ed-Fi-v5 → StateU-LIF`) | 83 | 83 | 0 |
| 49 (`StateU-LIF → Ed-Fi-v5`) | 70 | 70 | 0 |
| 50 (`StateU-LIF → CLR v2/OB v3`) | 30 | 30 | 0 |

The only two exceptions are target-**less**: transformations 1671 and 1672 in group 50
(`AchievementSubject.activityStartDate` and `.result`) — the same two malformed CLR rules behind
**#1144**, which the rule would have rejected at authoring time.

**What 3b requires us to enforce.** Gap F: export assigns the target by plain overwrite
(`transformation_service.py:1195`), and nothing today stops two mappings in a group from claiming
the same target field — when they do, one is silently dropped on export and the winner depends on
row order. 3b turns that from a silent data-loss defect into a rejected write, and it would have
caught #1144's two rules at authoring time. So the uniqueness rule on `(group, target path)` is
part of this decision, not a separate one.

**Why 3b over 3a.** Both give identity that survives source and expression edits, which is the
requirement. 3b gets there with no migration, no backfill and no new column, and its key is
readable — a human looking at a diff sees `Person.Name.firstName`, not a UUID. The rule it depends
on is one the data already keeps (183 of 183 well-formed mappings) and one we want enforced for its
own sake. 3a's advantage is surviving a target rename in place; under 3b a rename means a
a target rename costs a delete-and-create, which is the trade-off accepted above. Both need the
#746 remainder either way.

---

### 4. A round trip must be lossless

**Decision: yes — for everything the system supports.** Export a model, import it, and the result
matches what you started with. Anything that cannot survive that trip is a defect, not a
documented limitation.

**One scope limit, stated up front: lossless applies to JSONata expressions.** JSONata and
`LIF_Pseudo_Code` are the two values of `ExpressionLanguageType`
([`mdr_sql_model.py:26-28`](../../../components/lif/datatypes/mdr_sql_model.py#L26-L28)), and only
JSONata is executable — `LIF_Pseudo_Code` is the column default, so it is what a rule gets when
nobody chose a language. Those rules are drafts, not transformations, and carrying them across
installs is not something this epic owes anyone. A round trip is lossless for JSONata; a
non-JSONata rule is refused, clearly and by name.

Two things follow from the decision:

- **#1062 — keep the relationship's name.** When one entity points at another, the link has a
  name: `hasManager`, `relevantCourse`. The schema generator writes that link as a property called
  `Ref` + the target entity — so `hasManager` between Person and Employee is exported as
  `RefEmployee`, and the word `hasManager` is nowhere in the file
  ([`schema_generation_service.py:802`](../../../components/lif/mdr_services/schema_generation_service.py#L802)).
  Re-import it and the link comes back with no name at all. #1062 asks whether to fix that or
  write the loss down as intended; Decision 4 picks fixing it — the exported file has to carry the
  name so the same link comes back on the other side.
- **#1026 — say which property is a reference, instead of guessing from its name.** Today the
  reader recognizes a reference by spotting the `Ref` prefix, which is why #1062's name had to be
  crammed into the property name in the first place. An explicit marker gives the name somewhere
  to live, so this stops being optional: **#1062 cannot be fixed without it.**

And Gap F stops being a curiosity: two mappings writing the same target, with one silently
dropped, is data loss on a supported path.

---

### 5. How far does the ancestor chain investment go?

**Decision: 5a — one shared helper, and every name lookup walks the full chain.**

Gap E establishes the facts: the chain is unbounded, uncapped and cycle-capable — and **exactly
one function in the codebase actually walks it to the root.** That is `get_base_model_ids`, and
no import or export code calls it. Everywhere else that resolves a name looks at the anchor and
its immediate parent and stops: both name-lookup helpers, `valueset_service.py:216,250`, and
`transformation_service.py:1595,1603`. So on a two-deep model the shortcut is indistinguishable
from the real thing, and on a three-deep model those lookups silently cannot see the
grandparent. The question is how much to invest in fixing that.

| Option | Scope | Cost |
|---|---|---|
| **5a — Full chain everywhere** ✅ | One shared helper replaces both copies of `get_base_model_ids`, with a cycle guard; every name lookup takes the full chain | NEW-F as written; touches `valueset_service`, `transformation_service` and both name-lookup helpers |
| **5b — Full chain in import/export only** | The converter walks the chain; the one-hop helpers stay as they are | Smaller blast radius, but the same bug stays reachable from the other callers |
| **5c — Cap the depth at one, and enforce it** | Make today's implicit assumption true: reject creating a model whose parent itself has a parent | Cheapest; forecloses deeper extension hierarchies |

**Why 5a.** Name resolution is the whole portability mechanism — a reference in model C resolves by
searching C, then B, then A, nearest winning. If some lookups walk the chain and others stop at the
first parent, the same file imports differently depending on which code path reads it, which is the
class of bug this plan exists to retire. 5b leaves that inconsistency in place deliberately, and
the one-hop helpers (`valueset_service.py:216,250`, `transformation_service.py:1595,1603`) are
exactly the ones import and export call into. 5c is cheap but decides a product question by
accident: nothing says two-level extension is the intended ceiling, and enforcing it would make
today's oversight permanent. The blast radius of 5a is also smaller than it looks — see Sizing.

**Two fixes this includes.** Keep the `jinja_translation_service` copy of `get_base_model_ids` and
delete the other. It tests `is not None` where the `jinja_helper_service` copy tests truthiness —
which matters because **model ID 0 is a real model**, and a truthiness test reads it as "no parent"
and stops. Its regression test walks 7 → 0 → 2 → root and asserts the chain comes back as
`[7, 0, 2]`; under the truthiness version the same walk returns `[7]`, silently losing two
ancestors ([`test_jinja_translation_service.py:24-29`](../../../test/components/lif/mdr_services/test_jinja_translation_service.py#L24-L29)).
The `jinja_helper_service` copy has no callers. Neither has a **cycle guard**, and one is needed:
an unconstrained self-reference plus a free-typed parent number in the UI means a model can be made
its own ancestor, which hangs the walk.

---

## How a referenced model resolves

The file never names a model that gets looked up. Scope comes from the request, and every ID in the
file is discarded:

- **Anchor** — the model being imported into, from the request.
- **Ancestors** — read from the *target database's* own parent chain, never from the file.
- Every reference resolves by name within the anchor plus its ancestors, anchor winning a tie.

This is already how mappings import, so it is proven rather than proposed:
[`resolve_named_path`](../../../components/lif/mdr_services/transformation_service.py#L1558-L1590)
strips and ignores the model-ID prefix in each path, then delegates to
[`get_unique_entity`](../../../components/lif/mdr_services/entity_service.py#L603-L619), which
prefers the anchor's own row over an inherited one. The upload endpoint likewise takes the parent
model as a form field, never from the file. Using the same rule for schemas gives both halves of
the epic **one** portability rule instead of two. The only change needed is Decision 5: these
helpers currently see a single parent.

Two caveats on "proven":

- `get_unique_entity` decides whether to search the parent with a type-name check
  (`data_model_type == OrgLIF or PartnerLIF`,
  [`entity_service.py:608`](../../../components/lif/mdr_services/entity_service.py#L608)) — the
  same proxy behind #1321 — so it has to move to the structural test along with the chain walk.
- Not every shipped path fits the rule. `1:Credential,1:Credential.Image,16:~image.id` (group 50,
  model 17 → CLR) ends in a segment owned by model 16, which is not in model 17's ancestor chain,
  so anchor-plus-ancestors cannot resolve it. It is the path-level twin of the 25 inclusion rows
  that point outside the chain (Gap A). The format either supports a peer-model segment explicitly
  or refuses it by name — it must not resolve it by accident.

### Model identity is a safety check, not a lookup key

**#17** specifies that an upload removes anything absent from the file. So **uploading the wrong
file is a mass delete** — every name misses, so everything present is removed. The file must carry
its source model's identity, and import must refuse on mismatch.

- **Identity is three fields, not two**: name, version *and* contributing organization. Name plus
  version is unique across today's 21 models only by luck — the base model is literally named `LIF`
  from organization `LIF`, and nothing stops another organization publishing its own `LIF v1.0`.
- **Deletion must be limited to the anchor.** An element that resolved from an *ancestor* must
  never be deleted by an edit to the child model.
- **One shipped model has no organization.** Seed model 26 (`R1 Demo Source Data Model`) has
  `ContributorOrganization` NULL even though the column is declared required and the uniqueness
  rule indexes it. Since NULL never equals NULL, the identity check can never match that model.
  **Decision: refuse it.** An import whose model identity cannot be matched is rejected rather
  than guessed at.

### A hazard to watch while the work is in flight

#17 deletes anything absent from the uploaded file. Until export emits every kind of element, a
round-trip edit of an OrgLIF would **delete its entire inclusion set** — 206 rows for model 17, 94
for model 18.

Every element kind is in scope, so this is not a permanent constraint and the import/export flow
should stay clean rather than carry a partial-emission switch. Noted only because the phases may
run in parallel: **do not ship delete-on-import before export is complete.**

---

## Plan

Phases 2–3 and 5 can run in parallel once Phase 1 lands. Phase 6 needs 2 and 5 finished — you
cannot export a reference set you cannot export.

| Phase | Work | Demo |
|---|---|---|
| **0 — Unblock** | #1210, #1211, **#1321** | All three export failures gone, including PartnerLIF. |
| **1 — One converter** | **#1333** | *Not demoable* — a written contract. Gates everything, so keep it short. |
| **2 — Export writes the portable file** | #1008, #1026, #1062, **NEW-A**, **NEW-F** | Export a BaseLIF, a PartnerLIF, and each model of a three-deep chain as its own file; inclusions present, no database IDs. |
| **3 — Import reads it** | #762, #763, #764, #765, **NEW-H**, preflight preview | Import into a second install with different IDs; references intact. |
| **4 — Edit by import** | #17, #18 | Change a field in the file, re-import, watch it **update** instead of duplicating. |
| **5 — Mappings** | #1140, #1141, #1142, #1138, #891, #773, #774, **NEW-E**, **NEW-K** | Round-trip a mapping group end to end, carry value mappings across, and show a clear refusal for a group that has no JSONata. |
| **6 — Prove the round trip** | **NEW-D** | Export the shipped content, import into an empty install, assert it matches. **The epic's done-test.** |
| **7 — Keep it working** | #1063, **NEW-G** | Matrix green in CI across all four model types and a three-deep chain. |

Schema tickets in Phases 2–3: **#1008** name-based export so export output can be re-imported,
**#1026** explicit reference marker instead of a guessed naming convention, **#1062** keep
relationship names on export, **#762**–**#765** look up attributes, value sets, values and
entities by name instead of by the file's IDs.

Mapping tickets in Phase 5: **#1140** edit an existing mapping version on import, **#1141**
import diagnostics (re-scope first), **#1142** document the endpoint and round-trip contract,
**#1138** two conflicting copies of the same mapping-group record, **#891** more export tests,
**#773** import/export buttons in the mappings UI, **#774** a delete-group control. Mapping
portability is JSONata-only throughout, per Decision 4.

### Phase 1 — one converter (write this first)

There are **seven** hand-written conversions between file-shaped data and database rows — five for
schemas, two for mapping groups:

| Direction | Code |
|---|---|
| rows → OpenAPI file | `generate_openapi_schema` |
| OpenAPI file → rows | `create_data_model_from_openapi_schema` |
| rows → export record | `get_export_dto` / `export_datamodel` |
| import record → rows | `import_datamodel` |
| rows → rows (clone) | `clone_datamodel` |
| rows → mapping file | `get_paginated_transformations_for_a_group(make_exportable=True)` |
| mapping file → rows | `import_transformation_group` |

Two more readers never write rows but interpret the same rows by their own rules:

- the **OpenAPI generator** (first row above) re-derives schema structure from rows itself — the
  source of #1252 and #1334;
- the **Translator** reads mapping expressions through
  `GET /transformation_groups/transformations_for_data_models/`, whose query
  ([`get_paginated_all_transformations`](../../../components/lif/mdr_services/transformation_service.py#L614))
  filters neither `ExpressionLanguage` nor `GroupVersion` — so it merges every live group version for
  a model pair and receives `LIF_Pseudo_Code` expressions too, where export means one version,
  JSONata only.

The Translator's behavior is a **defect**, not a difference of opinion: it should read only the
latest version of a group, and only JSONata rules. Both halves reproduce on the seed — adding a
`2.0` group for pair 2 → 17 makes the read return rules from `1.0` and `2.0` together, and pair 4 →
1 returns group 3's `LIF_Pseudo_Code` rule — and the first is reachable today without hand-editing:
mapping import defaults to creating the next major version alongside the existing one
(`_next_major_group_version`). Filed as #1350 (see "Bugs found during Phase 1 research").

Both should eventually read through the converter's model, so the rules live in one place. Neither
migration is Phase 1 work, but it constrains Phase 1: the portable model must carry what those
readers need — inclusion flags, value `Value`s, relationship names, group version, expression
language. (The Jinja generator stays out of scope — see "Out of scope".)

**Every defect in this epic is two of them disagreeing.** #1026 and #1062 are the first two (one
bakes the reference into a property name and drops the relationship; the other guesses it back).
#1252 was internal to the first. #1008 is the middle pair. Gap A is the export and the clone
dropping inclusions differently. That is why fixing endpoints one at a time has not converged.

So Phase 1 makes the file the contract and the database an implementation detail, with exactly one
two-way converter between them. Export, import, upload, edit-by-upload, clone and the reference set
all become callers. One converter is also round-trip testable, a far stronger check than testing
endpoints.

It must settle:

- **Three kinds of reference** — within the anchor, into an ancestor, and **to a peer model**
  (what every value mapping needs, since a SourceSchema is in nobody's ancestor chain). The first
  two resolve by unique name; the third by the three-field model identity, which otherwise serves
  only as a safety check.
- **Which kinds of element the format carries — decided.** v1 carries **Entity and Attribute
  inclusions only**. It does not carry Constraint or Transformation inclusions,
  `DataModelConstraints`, or the attribute-level `Constraints` table; a file containing any of them
  is refused by name. The decision rests on the *code*, not the seed data (per "How to read this"):
  - **Constraint / Transformation inclusions.** `ElementType`
    ([`mdr_sql_model.py:38-42`](../../../components/lif/datatypes/mdr_sql_model.py#L38-L42))
    allows them, but the UI only ever creates Entity and Attribute inclusions (every
    `tmplCreateInclusion` call in `ModelExplorer.tsx`, guarded at `:1026`), upload only creates
    those two, `POST /inclusions/` does not check that such an element exists
    ([`inclusions_service.py:91-96`](../../../components/lif/mdr_services/inclusions_service.py#L91-L96)),
    and nothing reads them — every inclusion query filters to Entity or Attribute.
  - **`DataModelConstraints`** (`DatamodelElementType`, six members). API CRUD exists
    (`/datamodel_constraints`), but no UI path creates or shows one (`getModelConstraints` has no
    caller; `List.tsx`'s `showConstraints` is never passed), `ConstraintType` is free text nothing
    interprets, and the table has 0 rows.
  - **Attribute `Constraints`.** A model class only — no service, endpoint or UI — and 0 rows.
  - Both constraint tables trace to roadmap items that were never built, in
    [`mdr.md:199-202`](../../design/components/mdr.md) ("model constraints": excluding elements
    from an org model; org-specific validation rules). Exclusion is done today by *not* including
    an element. If either is built later, a new format version adds it. The #1333 spec carries this
    as historical context so the question is not re-opened.
- **Per-element origin** — owned here, inherited, or overriding an ancestor. Extensions are an
  overlay *between* models, not nesting; flattening loses that, and it is exactly what makes an
  extended model portable. The overlay has three parts: the inclusion row and its flags (on owned
  elements too — Gap A), the `ExtendedByDataModelId` links an extension adds between elements it
  does not own, and elements the extension owns outright.
- **Embedded vs pointed-at references** — the explicit marker from #1026, carrying relationship
  names per Decision 4.
- **A format version**, so today's files still read when the format changes.
- **The same-name ambiguity** that forced mappings and entity-attribute links out of the import
  record. `import_datamodel` keys entities and attributes by `Name`
  ([`import_export_service.py:219,241`](../../../components/lif/mdr_services/import_export_service.py#L219)),
  but `Name` is not unique — attributes hold 234 duplicate `(model, Name)` pairs. What the database
  enforces is `UniqueName` per model (`uq_attributes_uniquename_datamodelid_active`,
  `uq_entities_uniquename_datamodelid_active`), a dotted path such as `Assessment.identifier`. Keying
  on `UniqueName` removes the ambiguity rather than working around it.
- **Element keys for everything else**, taken from the database's own unique rules: value sets by
  `Name` within the model, values by `ValueName` within their value set, groups as in Decision 3.
- **Mapping path format** — paths still carry a source-database model ID that the importer throws
  away. Drop it or document it as advisory, and decide what happens to a segment outside the
  anchor's chain (see "How a referenced model resolves").

### Key the converter off structure, not the type name

Asked whether a LIF install with **no** BaseLIF, or with **two**, would break the conversion logic.
Checked: it would not — and the reason is worth building on.

Every type branch in the conversion code is really a **binary**: `Type in ["OrgLIF","PartnerLIF"]`
versus everything else. That is all 12 branches in the schema generator and all 8 in the upload
reader (16 and 10 *lines* mention the type names; the rest are comments). The same proxy appears
19 more times in the services those two call — 6 in `attribute_service.py` and 13 in
`entity_service.py`, including both name-lookup helpers (`get_unique_attribute:161`,
`get_unique_entity:608`) that mapping import resolves paths through. What the code is actually
asking each time is *"does this model have a parent?"* — and the type name is only a proxy for it,
guaranteed by the creation rule that gives OrgLIF and PartnerLIF a parent and denies BaseLIF and
SourceSchema one.

The proxy does not mean the branches are *simple*. Several do not test parentage at all once
inside: they scope by "has an inclusion row for this model" and turn a missing row into a 404.
Swapping the condition is safe for new converter code; retrofitting it into the generator is not a
mechanical find-and-replace.

Two places already use the structural test directly rather than the proxy:
`search_service.py:37,47` splits models on `BaseDataModelId` being null or not, and
`transformation_service.py:132` calls a model "self-contained" when it has no parent.

So:

- **No BaseLIF** — nothing breaks. The converter never asks where the BaseLIF is; it asks whether
  the anchor has a parent. A SourceSchema-only install converts fine.
- **Two BaseLIFs** — nothing breaks either. Each extended model names its own parent, so two
  independent chains coexist. The schema generator already anticipates this: comments at
  `schema_generation_service.py:544` and `:601` say an extended model "can have entities from
  multiple base data models."

What *would* break in both cases is outside the converter: the UI hardcodes the parent to model
`1` (`Dialog.tsx:94`, `DataModelSelector.tsx:93`), and the one-hop helpers in Gap E see only the
nearest parent.

**Therefore: the converter keys off structure — has a parent, or does not — never off the type
name.** That is strictly more robust, and it retires a class of bug by construction: the PartnerLIF
export failure is exactly a type-name check (`Type == "OrgLIF"`) standing in for "has a parent".

---

## New tickets

| ID | Title | Why |
|---|---|---|
| **NEW-A** | Export inclusion flags for every element an extended model exposes — owned, inherited and out-of-chain | Gap A; also fixes `clone_datamodel` |
| **NEW-D** | Round-trip proof: export shipped content → import to empty install → compare | Decision 2 |
| **NEW-E** | Say why a group cannot be exported | Gap C; one 400 covers three different causes, and tells the user to do the wrong thing |
| **NEW-F** | One ancestor-chain helper, with a cycle guard; every lookup uses the full chain | Gap E, Decision 5. #1333 builds the helper (its three-deep round trip needs it); NEW-F moves the other callers onto it |
| **NEW-G** | JSON-file import test suite (MDR only) | Goal 4; extends `conftest.py` |
| **NEW-H** | Import in a single transaction | Per-row commits can leave a half-imported model |
| **NEW-I** | Enforce one mapping per target field within a group | Decision 3; makes `(group, target path)` a usable identity, and closes the #746 remainder |
| **NEW-J** | Preflight preview: what an import would create, update and delete — including the mappings it would break | Decision 1; replaces #768/#775 |
| **NEW-K** | Carry value mappings as peer-model references | Gap A; every one is cross-model, so it needs the third reference kind |

---

## Sizing

Most are 1–3 days and demoable on their own. Three are not, and are flagged rather than disguised:

| Ticket | Why not demoable | What to do |
|---|---|---|
| **#1333** | A spec, a converter with no endpoint, and its round-trip suite show nothing to a user | Demo its first consumer instead; the file-in → rows → file-out suite is the evidence |
| **#746** (remainder) | A uniqueness rule only demos as a rejected duplicate | Pair with NEW-I, which needs it |
| **NEW-D** (extractor half) | Invisible until the comparison runs | Pair the two halves |

**NEW-F is narrower than it looks.** It changes shared code, but `mdr_services` is packaged by
exactly one project (`lif_mdr_api`) and imported by exactly one service (`mdr_restapi`) — so the
risk is many call sites inside MDR, not a silent break in another service. Still worth checking the
deploy path filters (#1171 — shared code changes that deploy workflows don't rebuild).

**#1141 must be re-scoped before it is estimated** — several items already shipped in #1136, one
was replaced by a simpler rule, and one shipped with different behavior than its plan describes.

---

## Bugs found during Phase 1 research — file outside the epic

Found while grounding #1333 (`main` @ `3ef6d84`) and reproduced against the `backup.sql` seed on a live Postgres. None
blocks portability, so each is its own ticket rather than epic scope.

| Bug | Where | Reproduced |
|---|---|---|
| A PartnerLIF's OpenAPI schema includes attributes it never included, and its full-metadata export 404s | The inclusion filter in `get_attributes_with_association_metadata_for_entity` has no `ExtDataModelId` condition ([`attribute_service.py:469-473`](../../../components/lif/mdr_services/attribute_service.py#L469-L473)), so an inclusion by *any* extension counts. | Model 18: 48 attributes pass the filter without a model-18 inclusion. Attribute 800 (`Credential.expirationDate`, included only by model 17) appears in model 18's schema; with `include_attr_md=True` generation returns 404 "Inclusion not found for Attribute ID 800". |
| Cloning a model copies only the first group's rules | `return` inside the group loop ([`import_export_service.py:664`](../../../components/lif/mdr_services/import_export_service.py#L664)) | Cloning model 17's groups: 6 groups copied, 0 of 5 live rules. |
| Updating a value mapping can create a duplicate within a group | The duplicate-check query for the known-group branch is built but never executed ([`value_mapping_service.py:192-208`](../../../components/lif/mdr_services/value_mapping_service.py#L192-L208)) | Two mappings in group 25; updating one onto the other's pair succeeded, leaving two live rows for the same pair and group. |
| The Translator merges every live version of a group and evaluates non-JSONata rules as JSONata (#1350) | `get_paginated_all_transformations` filters neither `GroupVersion` nor `ExpressionLanguage` ([`transformation_service.py:614`](../../../components/lif/mdr_services/transformation_service.py#L614)); the Translator then compiles every expression as JSONata, skipping (and counting) any that fail ([`translator/utils.py:44-49`](../../../components/lif/translator/utils.py#L44-L49), [`core.py:51-62`](../../../components/lif/translator/core.py#L51-L62)) | With a `2.0` group added for pair 2 → 17, the read returned rules from `1.0` and `2.0`; pair 4 → 1 returned group 3's `LIF_Pseudo_Code` rule. |

Also noted, not a bug: `generate_openapi_schema` applies `public_only` to `ext_inclusions_query`
instead of `inclusions_query` at `schema_generation_service.py:681,709`. The reassigned variable is
never used again and the attribute list is already filtered upstream, so it has no effect — dead
code to delete when the generator is next touched.

---

## Tickets in the epic that do not serve portability

Four of the epic's tickets do not move data portability forward. None is worthless; they just
shouldn't be counted as epic scope or hold up the done-test.

| Ticket | What it is | Recommendation |
|---|---|---|
| **#646** — spike: research & design for export/import | A 2025 planning spike whose questions this document now answers | **Close**, superseded |
| **#662** — export/import translations into MDR | The original one-line ask that became this epic | **Close**, superseded by #1223 |
| **#1138** — two conflicting copies of the same mapping-group record | Code hygiene found by type-checking work, not a portability defect | **Keep, outside the epic.** It is a genuine trap — a future edit to the wrong copy silently does nothing — and it sits in the import path, so it is worth doing before Phase 5 rather than as part of it |
| **#774** — a delete-group control in the UI | CRUD convenience. It supports *experimenting* with import (delete a bad group and retry) but nothing in the round trip needs it | **Keep, low priority.** Real value is operator quality of life during Phase 5 |

Everything else in the epic earns its place. The two that look like overhead do not: **#1142**
(document the endpoint and the round-trip contract) is the only place the contract gets written
down for anyone outside this document, and **#891** (more export tests) guards the half of the
round trip that had no tests at all.

---

## Out of scope for this epic: moving MDR to a document store

If the exported files are the contract, should MDR store documents (MongoDB) instead of rows?
That is **#1132**'s question, and it stays there. The narrow claim here is only that **portability
does not need it** — not that the move is wrong.

1. **The file format hides the storage engine, so swapping it changes nothing here.** Exported
   files have to come out the same either way. Once the format is fixed, what sits behind it is
   invisible to the thing this epic is trying to fix.
2. **Portability is solvable on Postgres.** Everything in this plan — name-based references, the
   ancestor chain, a stable mapping identity, a lossless round trip — is reachable without
   touching the storage layer, which is what the phases above lay out.

> *Superseded reasoning, kept so it is not repeated:* an earlier draft argued that the 8 name-
> uniqueness rules behind #746 would degrade into racy application checks in a document store.
> That is wrong — MongoDB has unique indexes and partial unique indexes, so those rules port. The
> argument is withdrawn. It was never load-bearing: the conclusion rests on points 1 and 2 above —
> the format hides the engine, and Postgres is sufficient — neither of which depends on it.

One genuinely open question belongs on **#1132**, not here: extensions and inclusions are an
overlay *between* models, not nesting, and a document is a tree. Flattening an OrgLIF into one
loses owned-vs-inherited-vs-overriding, which is exactly what an export must keep — so a document
model would have to carry the overlay explicitly. Whether that is a cost or a clarification is a
storage-layer design call, and it would have to reckon with the ancestor chain that Decision 5
keeps.

**The valuable half was kept** and is now Phase 1: a file-shaped conversion layer over SQL. It is
also the thing that would make #1132 tractable later — once the file is the contract, the storage
engine underneath it is replaceable.

---

## Out of scope

- Frontend work other than #18 (update-by-upload button), #773 (mapping import/export UI) and
  #774 (delete a mapping group), which are all in scope and phased above.
- Moving files between installs — a registry, signing, publishing. This makes the file portable;
  carrying it is someone's `scp`.
- Jinja translation services.
- Tenant schema provisioning, a separate path from import/export.

---

## References

Epic **#1223**. Merged groundwork: **#1007** (read inlined references on upload), **#1006** (fix
the native import path), **#1136** (mapping import, first layer). Prior plan:
[`.claude/plans/772-import-transformation-groups.md`](../../../.claude/plans/772-import-transformation-groups.md).
