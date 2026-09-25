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
  name; mappings have no usable name, so they get a generated key that travels with them
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
#1210. The third is untracked and currently hidden behind #1210, which fails first — so PR #1212
will expose it. Seed model 18 (`Org2 LIF`) triggers it. None of the three has a regression test,
and both tracked ones were reported by an outside contributor rather than caught in CI.

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
`clone_datamodel` as the reference implementation for ID remapping; it is, for what it covers, but
it is **itself incomplete for extended models**.

An exported OrgLIF or PartnerLIF therefore loses its entire inclusion set — the thing that makes it
an extension (206 rows for model 17, 94 for model 18). Biggest correctness hole in the schema half.

**But the two tables need different fixes.** Inclusions fit the anchor-plus-ancestors rule
(models 17 and 18 include elements of model 1, their parent). Value mappings do not. Measured on
active rows: **all 2,347 are cross-model, none are same-model.** Sources are ten SourceSchemas
(2, 3, 4, 7, 9, 10, 12, 14, 15, 25); targets are BaseLIF model 1 and PartnerLIF model 18. A
SourceSchema has no parent and appears in nobody's ancestor chain, so a value mapping's source end
is **neither the anchor nor an ancestor**.

That needs a third kind of reference in the file format — a **peer-model reference**, resolved by
the three-field model identity — and it behaves like the mapping half of the epic, not the schema
half. So inclusions and value mappings get separate tickets in separate phases.

### B. There is no update path for schemas

`import_datamodel` only ever creates
([`import_export_service.py:196`](../../../components/lif/mdr_services/import_export_service.py#L196)).
Goal 3 has no backing code at all. **#17** (backend: update a schema by upload) and **#18**
(frontend button for it) describe the flow but predate this work.

### C. Seven of nine mapping groups cannot be exported

[`transformation_endpoint.py:234-246`](../../../bases/lif/mdr_restapi/transformation_endpoint.py#L234-L246)
exports only JSONata rules. A group with none returns **400 — "There are no valid transformations
to export for this group / version. Please add a transformation to this group's version and retry
the export."** Only groups 25 and 26 export today.

The filter is real and wrong, but it is not why the other seven fail. Measured on active rows,
**six of the nine groups are empty** (12, 15, 16, 22, 23, 24 have no live rules at all) and return
the same 400 from the `total_count == 0` check whether the filter exists or not. Only **group 3**
is blocked by the filter itself — one rule, written in `LIF_Pseudo_Code`.

So removing the filter takes exportable groups from 2 to 3, not to 9. The remaining six are empty;
getting them to export means *putting mappings in them* — authoring seed or test data — which is a
content task, not a code fix.

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

1. **A three-deep model cannot be exported at all** — the export record has exactly two slots,
   parent and child. There is nowhere to put a grandparent. It needs an ancestor *list*.
2. **Exporting any PartnerLIF fails** — the third row in the table above.
3. **Name lookups must search the whole chain**, which is what `get_base_model_ids` already does
   and no import/export code calls.

None of the 21 seed models is three deep, which is why this stayed invisible — and why the test
matrix needs a three-deep fixture.

### F. A mapping may have more than one target, and export keeps only the last

Export assigns the target by plain overwrite (`transformation_service.py:1195`), so a second target
silently disappears. Nothing prevents a second one: there is no uniqueness rule on mapping
attributes, and an `OutputAttributesCount` column exists. Of the six live mappings, five have
exactly one target and one (transformation 1189, group 3) has none — a sample, not a rule. Under
Decision 4 (lossless) this is a defect.

---

## Tickets already satisfied

| Ticket | Evidence | Action |
|---|---|---|
| **#1252** — export 500 on a nested embedded parent | Fixed and **already closed** on GitHub; the two functions now agree on naming ([`schema_generation_service.py:355-400`](../../../components/lif/mdr_services/schema_generation_service.py#L355-L400)). | **None — listed so it is not re-opened** |
| **#717** — fetch the schema from MDR instead of a file | Done. Services load from MDR at startup, with a documented dev-only file fallback. | **Close as stale** |
| **#746** — enforce unique names on anything exportable | Mostly done in the database: 8 uniqueness rules already cover models, entities, attributes, value sets, values, mapping groups and both link tables. | **Re-scope** to the one gap: mapping names |
| **#1063** — round-trip test matrix | One bullet ("make sure it runs in CI, not skipped") is already true: CI run `35801872026` ran the round-trip test against real Postgres, 861 passed, zero skipped. | **Drop that bullet**, keep the rest |

The last one matters: **the database-backed test harness goal 4 needs already exists and already
runs in CI.** The JSON-import suite extends `conftest.py` rather than building anything new.

---

## Decisions

**1. Close #768 and #775; open one replacement.**
#768 (accept a default model ID and an ID map on upload) and #775 (list the model IDs found in an
upload) both exist to cope with IDs in files. Neither survives: the anchor comes from the request,
and the upload endpoint already takes the parent model as a form field. Replace them with a
**preflight preview** — before an import runs, show which models the file refers to and what would
be created, updated and **deleted**.

**2. Keep the round-trip proof; defer the migration slimming.**
`backup.sql` should track the latest migration. Actually pulling seed data out of the migrations is
a **separate effort** after portability lands. This epic still proves the end state — export the
shipped content, import it into an empty install, assert the result matches — without removing
anything from the migrations. Same guarantee, no migration surgery, and the follow-on effort
inherits a working extractor.

**3. Identify a mapping by a generated portable key.**
Names cannot do it: **nothing enforces mapping-name uniqueness** — that absence is exactly the
#746 remainder — and names are editable, so a name is not an identity. (The seed data does hold
118 duplicate (group, name) pairs, but every one is soft-deleted version history; on active rows
there are zero, so do not lean on that figure.) Target path cannot do it either — a mapping may
have several sources and, per Gap F, possibly several targets.

Add a `PortableKey` column to mappings: a random UUID, generated in **Python at creation**, written
into exports, and **preserved on import rather than regenerated**. That last point is the whole
mechanism. It stays stable through any edit to paths or expressions, which a content-derived hash
would not — editing a source path would change the hash, and the import would delete and recreate
the row instead of updating it, losing its notes and history.

Details: generate in application code, not SQL — the key must be **preserved on import**, so
application code owns it either way, and a SQL default invites someone to regenerate it. Make the
key unique **per group**, so cloning a group into a new version can keep keys and let you diff versions. Backfill with `WHERE "PortableKey" IS NULL` so the migration can be replayed safely.
When no key is present (hand-written files, older exports), fall back to matching on target plus sorted sources — as a readable tuple, not a hash.

Only mappings need this. Entities, attributes and value sets already have a portable identity in
their unique name; mappings are the outlier, which is what #1140 ran into.

**4. A round trip must be lossless.**
So **#1062** (relationship names dropped when a reference is exported) carries the names rather
than documenting the loss. Two knock-ons: **#1026** (replace the guessed `Ref` naming convention
with an explicit marker) becomes **required**, since a name cannot survive in a format that drops
it — and Gap F becomes a defect rather than a curiosity.

**5. Follow the ancestor chain everywhere**, not just in import/export. One shared helper replaces
the two copies of `get_base_model_ids` — keeping the `jinja_translation_service` version, which is
the corrected and tested one — with a cycle guard added, and every name lookup takes the full
chain.

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
| **0 — Unblock** | #1210, #1211, **NEW-C** | All three export failures gone, including PartnerLIF. |
| **1 — One converter** | **NEW-B** | *Not demoable* — a written contract. Gates everything, so keep it short. |
| **2 — Export writes the portable file** | #1008, #1026, #1062, **NEW-A**, **NEW-F** | Export a BaseLIF, a PartnerLIF and a three-deep OrgLIF; inclusions present, no database IDs. |
| **3 — Import reads it** | #762, #763, #764, #765, **NEW-H**, preflight preview | Import into a second install with different IDs; references intact. |
| **4 — Edit by import** | #17, #18 | Change a field in the file, re-import, watch it **update** instead of duplicating. |
| **5 — Mappings** | #1140, #1141, #1142, #1138, #891, #773, #774, **NEW-E**, **NEW-K** | Export group 3 (blocked by the filter today), round-trip one end to end, and carry value mappings across. |
| **6 — Prove the round trip** | **NEW-D** | Export the shipped content, import into an empty install, assert it matches. **The epic's done-test.** |
| **7 — Keep it working** | #1063, **NEW-G** | Matrix green in CI across all four model types and a three-deep chain. |

Schema tickets in Phases 2–3: **#1008** name-based export so export output can be re-imported,
**#1026** explicit reference marker instead of a guessed naming convention, **#1062** keep
relationship names on export, **#762**–**#765** look up attributes, value sets, values and
entities by name instead of by the file's IDs.

Mapping tickets in Phase 5: **#1140** edit an existing mapping version on import, **#1141**
import diagnostics (re-scope first), **#1142** document the endpoint and round-trip contract,
**#1138** two conflicting copies of the same mapping-group record, **#891** more export tests,
**#773** import/export buttons in the mappings UI, **#774** a delete-group control.

### Phase 1 — one converter (write this first)

"Converter" rather than "translator" throughout — LIF already has a Translator service, and this
is a different thing.

There are **five** hand-written conversions between file-shaped data and database rows:

| Direction | Code |
|---|---|
| rows → OpenAPI file | `generate_openapi_schema` |
| OpenAPI file → rows | `create_data_model_from_openapi_schema` |
| rows → export record | `get_export_dto` / `export_datamodel` |
| import record → rows | `import_datamodel` |
| rows → rows (clone) | `clone_datamodel` |

**Every defect in this epic is two of them disagreeing.** #1026 and #1062 are the first two (one
bakes the reference into a property name and drops the relationship; the other guesses it back).
#1252 was internal to the first. #1008 is the middle pair. Gap A is the export and the clone
dropping inclusions differently. That is why fixing endpoints one at a time has not converged.

So Phase 1 makes the file the contract and the database an implementation detail, with exactly one
two-way converter between them. Export, import, upload, edit-by-upload, clone and the reference set
all become callers. One converter is also round-trip testable, a far stronger gate than testing
endpoints.

It must settle:

- **Three kinds of reference** — within the anchor, into an ancestor, and **to a peer model**
  (what every value mapping needs, since a SourceSchema is in nobody's ancestor chain). The first
  two resolve by unique name; the third by the three-field model identity, which otherwise serves
  only as a safety check.
- **Which kinds of element can be inherited.** The type has four members — attribute, entity,
  constraint and mapping — but the shipped data only ever uses the first two, and the column has no
  foreign key. Handle all four rather than inferring scope from the seed data.
- **Per-element origin** — owned here, inherited, or overriding an ancestor. Extensions are an
  overlay *between* models, not nesting; flattening loses that, and it is exactly what makes an
  extended model portable.
- **Embedded vs pointed-at references** — the explicit marker from #1026, carrying relationship
  names per Decision 4.
- **A format version**, so today's files still read when the format changes.
- **The same-name ambiguity** that forced mappings and entity-attribute links out of the import
  record.
- **Mapping path format** — paths still carry a source-database model ID that the importer throws
  away. Drop it or document it as advisory.

### Key the converter off structure, not the type name

Asked whether a LIF install with **no** BaseLIF, or with **two**, would break the conversion logic.
Checked: it would not — and the reason is worth building on.

Every type branch in the conversion code is really a **binary**: `Type in ["OrgLIF","PartnerLIF"]`
versus everything else. That is 15 of the 16 branches in the schema generator and all 10 in the
upload reader. What the code is actually asking each time is *"does this model have a parent?"* —
and the type name is only a proxy for it, guaranteed by the creation rule that gives OrgLIF and
PartnerLIF a parent and denies BaseLIF and SourceSchema one.

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
| **NEW-A** | Export base-model inclusions | Gap A; also fixes `clone_datamodel` |
| **NEW-B** | Design: portable file format + the single converter | Phase 1 contract |
| **NEW-C** | Fix the PartnerLIF export failure | Gap E; sibling of #1210/#1211, exposed by PR #1212 |
| **NEW-D** | Round-trip proof: export shipped content → import to empty install → compare | Decision 2 |
| **NEW-E** | Export non-JSONata mapping groups | Gap C; unblocks 7 of 9 groups |
| **NEW-F** | One ancestor-chain helper; every lookup uses the full chain | Gap E, Decision 5 |
| **NEW-G** | JSON-file import test suite (MDR only) | Goal 4; extends `conftest.py` |
| **NEW-H** | Import in a single transaction | Per-row commits can leave a half-imported model |
| **NEW-I** | Add `PortableKey` to mappings, with backfill | Decision 3 |
| **NEW-J** | Preflight preview: what an import would create, update and delete | Decision 1, replaces #768/#775 |
| **NEW-K** | Carry value mappings as peer-model references | Gap A; every one is cross-model, so it needs the third reference kind |

---

## Sizing

Most are 1–3 days and demoable on their own. Three are not, and are flagged rather than disguised:

| Ticket | Why not demoable | What to do |
|---|---|---|
| **NEW-B** | A design document shows nothing | Keep it to one sitting; demo its first consumer instead |
| **#746** (remainder) | A uniqueness rule only demos as a rejected duplicate | Pair with Decision 3, which it supports |
| **NEW-D** (extractor half) | Invisible until the comparison runs | Pair the two halves |

**NEW-F is narrower than it looks.** It changes shared code, but `mdr_services` is packaged by
exactly one project (`lif_mdr_api`) and imported by exactly one service (`mdr_restapi`) — so the
risk is many call sites inside MDR, not a silent break in another service. Still worth checking the
deploy path filters (#1171 — shared code changes that deploy workflows don't rebuild).

**#1141 must be re-scoped before it is estimated** — several items already shipped in #1136, one
was replaced by a simpler rule, and one shipped with different behavior than its plan describes.

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

## Considered and rejected: moving MDR to a document store

If the exported files are the contract, should MDR store documents (MongoDB) instead of rows?
Recorded so it is not re-proposed each time export hurts.

1. **The constraint defeats the change.** Exported files must stay identical. If the file format is
   fixed, the storage engine is by definition hidden behind it — the migration cannot move what
   this epic cares about.
2. **It would weaken the foundation.** Name uniqueness (#746) is enforced today by 8 database
   rules. In a document store those become application checks, racy under concurrent import — right
   as we start depending on them. Tenant separation is equally Postgres-specific.
3. **It would obscure the confusing part.** Extensions and inclusions are an overlay *between*
   models, not nesting. A document is a tree; flattening an OrgLIF into one loses
   owned-vs-inherited-vs-overriding, which is exactly the information an export must keep. The
   document must carry the overlay anyway — at which point it is a serialization of the relational
   structure, not an escape from it.

MongoDB already serves the query cache here, which is the opposite kind of problem: opaque blobs,
expiry, no cross-record rules. MDR metadata is a graph with inheritance and hard uniqueness rules.

**The valuable half was kept** and is now Phase 1: a file-shaped conversion layer over SQL.

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
