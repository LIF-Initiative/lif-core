# Issue #772 — Import Transformation Group endpoint

Expose an MDR endpoint that imports a portable Transformation Group JSON (the counterpart
of the already-merged export, #771), resolving portable **name** paths back to local
database IDs and validating them with the PR #843 chain-validation logic.

## Goal (from the ticket)

A transformation import request shall:

- Require AuthN (satisfied by the MDR base's existing auth middleware — no per-route wiring).
- Include a JSON file describing a Transformation Group.
- Specify a Transformation Group (by **ID**) to clone or edit. Source and target data model
  IDs are derived from that group ID. **This group ID is the *only* ID matched against the DB.**
- Specify a version:
  - **blank** → clone the group (metadata only, not its transformations), set version to the
    **next major**, and add the transforms from the import file.
  - **known** `(source, target, version)` → treat as an **edit** (remove existing transforms
    not present in the file).
  - **specified-but-unknown** → create a new group at that explicit version (decided in
    clarification; blank still means next-major, known still means edit).
- Specify boolean `allowMissingPaths`.
- Responses:
  - On success, return the affected Transformation Group ID.
  - For any source/target attribute path that cannot be matched to existing entities/attributes:
    - `allowMissingPaths=true` → proceed with the import (skipping the affected transformation).
    - otherwise → fail the call and make **no** changes.
    - Either way, return the full list of non-matches.

## Data-portability requirement

IDs may be leveraged **relative to the import file**, but **no ID in the import file except the
transformation-group ID may be matched to IDs in the database.**

This is enforced by the export/import contract already in place:

- Export ([`_resolve_entity_id_path_to_named_path`](../../components/lif/mdr_services/transformation_service.py))
  turns a numeric `EntityIdPath` (`5,-12`) into comma-joined portable segments
  `"{DataModelId}:{~}{UniqueName}"`, where `~` marks the terminal attribute.
- The numeric `{DataModelId}` prefix is the **originating model ID from whatever instance
  authored the file** and must never be matched against the DB. Proof:
  [`reference_data/transformations/StateU_LIF_v1.0_Ed-Fi_v5.json`](../../reference_data/transformations/StateU_LIF_v1.0_Ed-Fi_v5.json)
  has `SourceDataModelId: 17` yet its source paths are prefixed `1:`.
- `UniqueName` is a dotted hierarchical path (e.g. `person.employment.preferences`,
  `Assessment.AssessmentIdentifier`), **unique only within a data model** — the same name can
  exist in multiple models. So resolution must be scoped to a known anchor model.

Import therefore resolves each segment's `UniqueName` (ignoring the numeric prefix) against the
**anchor data model** (source or target, derived from the group ID) plus its base model.

## Key facts confirmed in the codebase

- **PR #843 reuse target**: [`check_transformation_attribute(session, anchor_data_model, id_path)`](../../components/lif/mdr_services/transformation_service.py)
  validates a **numeric** `id_path` against an anchor model — existence, non-deletion,
  inclusion, and the association/extension chain. Import resolves names → numeric, then hands
  off to this function unchanged.
- **Reverse-resolution primitive exists**: [`get_unique_entity`](../../components/lif/mdr_services/entity_service.py)
  resolves `(UniqueName)` scoped to `anchor model OR its base model` per model type. A mirror
  `get_unique_attribute` will be added.
- **DTO stub** `ImportTransformationGroupDTO` exists in
  [`import_export_dto.py`](../../components/lif/mdr_dto/import_export_dto.py) but does not match
  the actual export shape and is unused; the import request/response DTOs will round-trip the
  export output shape.
- **Session** is one-per-request (`async with async_session()`, `expire_on_commit=False`), so a
  single transaction can span the whole import.
- **No DB uniqueness** on the group triplet `(SourceDataModelId, TargetDataModelId, GroupVersion)`
  — only an app-level check-then-insert in `create_transformation_group`, which races.

## Design decisions (confirmed with product/user)

| Topic | Decision |
|-------|----------|
| Request shape | **JSON body + query params**: `POST /transformation_groups/{transformation_group_id}/import?version=&allowMissingPaths=false`, body = exported group JSON. |
| Unknown version | Specified-but-unknown → **create a new group at that version**. Blank → next major. Known → edit. |
| `allowMissingPaths=true` granularity | **Skip the entire transformation** if any of its source/target paths is unmatched; import the rest; always return the full non-match list. |
| Name-resolves-but-chain-invalid | Fold into the **same non-match list**, governed by `allowMissingPaths`. |

## Core mechanism: single transaction, streaming validate-and-stage, one commit

Rationale (revised after the concurrency review): a "validate-all then apply-all" two-phase
split risks a TOCTOU gap if the two phases straddle commits, and committing per-transformation
would violate the ticket's "make no changes on failure" rule. Instead do everything in **one
transaction**, validate-and-*stage* each transformation as we go, and commit exactly once:

```
for t in file.transformations:
    resolve each source/target named path -> numeric id_path   # reads only
    check_transformation_attribute(...)                        # PR #843 reuse, reads only
    if any non_match: record it; skip this whole transformation
    else: session.add(rows...)   # stage; flush to obtain Ids — NO commit
# after the loop:
if non_matches and not allow_missing_paths:
    await session.rollback()     # zero changes, per ticket
    return { success: false, TransformationGroupId: null, missingPaths: [...] }
await session.commit()           # single commit
return { success: true, TransformationGroupId: <id>, missingPaths: [...] }
```

Benefits: the check/apply TOCTOU window collapses (one MVCC snapshot); atomicity is just
`rollback()`; single pass; tiny lock footprint (MVCC reads of reference data don't block;
we only insert new rows).

To own the transaction boundary, `create_transformation_group` / `create_transformation` gain an
optional `commit: bool = True` (flush-to-get-Ids when `False`, preserving all existing callers);
the importer passes `commit=False`.

### Concurrency guard (separate from transaction structure)

Transaction structure alone does not stop two users creating the same
`(source, target, version)` group concurrently — but a suitable DB guard **already exists**:
`ux_transformationsgroup_model_id_version_active`, a partial unique index on
`(GroupVersion, SourceDataModelId, TargetDataModelId) WHERE "Deleted" IS NOT TRUE`, defined in
`V1.1__metadata_repository_init.sql` (line 18520) and present in `backup.sql`. Column order is
irrelevant to uniqueness, so it fully covers this. **No new migration is needed** (an earlier draft
added a redundant one; removed). The losing racer's `commit()` fails with an `IntegrityError`
translated to a clean **409** — covering both the duplicate-create race and the "two clones both
computed next-major = 2.0" race.

## Resolution: named path → numeric id_path (reverse of the export)

`resolve_named_path_to_id_path(session, named_path, anchor_data_model) -> str`:

1. Split `named_path` on `,`. Each segment is `"{num}:{~}{UniqueName}"`.
2. **Strip and ignore the `{num}:` prefix** (portability). Detect `~` → attribute (must be last
   segment only).
3. Entity segment → `get_unique_entity(session, unique_name, anchor.Id, anchor.BaseDataModelId, anchor.Type)`.
4. Terminal attribute segment → new `get_unique_attribute(...)` (mirror of `get_unique_entity`).
5. On any miss → raise a typed "unmatched" signal captured as a non-match.
6. Build numeric id_path: entities as `+Id`, terminal attribute as `-Id`, comma-joined.
7. Caller then runs `check_transformation_attribute(session, anchor_data_model, id_path)`; a
   chain-validation failure is also recorded as a non-match (per decision above).

Non-match record shape: `{ transformationName, attributeType (Source|Target), namedPath, reason }`.

## Layered implementation

### Layer 1 — MVP: clone-mode import + full reuse of #843 validation + concurrency safety

Covers blank-version (→ next major) and specified-unknown-version (→ that version), i.e.
create-a-new-group — the most common portability flow and it sidesteps edit/reconcile.

- `get_unique_attribute()` in `attribute_service.py` — mirror of `get_unique_entity`.
- `resolve_named_path_to_id_path()` in `transformation_service.py` — reverse of
  `_resolve_entity_id_path_to_named_path`; prefix-ignoring; anchor+base scoped.
- `_next_major_group_version(session, source_id, target_id)` helper.
- `commit: bool = True` param added to `create_transformation_group` / `create_transformation`.
- `import_transformation_group(session, group_id, file, version, allow_missing_paths)` — the
  single-transaction streaming orchestrator; clones group metadata from the referenced group,
  adds resolved transforms, honors skip/non-match rules; single commit / rollback.
- Concurrency guard: reuse the existing `ux_transformationsgroup_model_id_version_active` partial
  unique index (no new migration); translate its `IntegrityError` to 409.
- `POST /{transformation_group_id}/import` endpoint (JSON body + query params); translate
  `IntegrityError` → 409.
- Request/response DTOs (round-trip the export output shape).
- Tests: unit (resolution round-trip, prefix-ignoring, next-major, missing-path skip vs abort)
  + endpoint **export→import round-trip** reusing the `DatasetTransformWithEmbeddings` fixtures
  in `test/bases/lif/mdr_restapi/test_transformation_endpoint.py`.

### Layer 2 — Edit mode (known version)

Reconcile against the existing group in the same single transaction: add/update file transforms,
soft-delete existing transforms absent from the file (match key = transformation `Name`,
documented). Tests for edit + delete-not-in-file.

### Layer 3 — Robustness & diagnostics

- Disambiguate `UniqueName` collisions across anchor+base using the file's **relative** prefix
  grouping (segments sharing a prefix share an originating model).
- Distinguish `not-found` vs `chain-invalid` in the non-match `reason`.
- Guardrails:
  - Non-JSONata transforms: **skip and log a warning** (mirror export's out-of-scope rule) —
    not silent, so operators can see what was dropped.
  - Empty/malformed file (unparseable JSON, missing required fields): **fail with 400**, no changes.
  - Empty result (file has no JSONata transformations, or every transformation was skipped for
    missing paths under `allowMissingPaths=true`): **fail with 400**, no changes — a group with no
    transformations is not allowed (mirrors the export side, which refuses to emit an empty group).
  - Edge-case tests for each.

### Layer 4 — Docs

Update `bases/lif/mdr_restapi/README.md`, services-overview, and the transformation-portability
design doc (round-trip contract); update `docs/INDEX.md` if a new doc is added.

## Files touched

- `components/lif/mdr_services/transformation_service.py` — resolution, orchestrator,
  next-major, `commit=` param.
- `components/lif/mdr_services/attribute_service.py` — `get_unique_attribute`.
- `bases/lif/mdr_restapi/transformation_endpoint.py` — new endpoint.
- `components/lif/mdr_dto/import_export_dto.py` (or a transformation DTO module) — request/response DTOs.
- `test/…` — mirrored unit + endpoint tests.

(No DB migration: the required partial unique index already exists — see the concurrency-guard note.)

## Out of scope (inherited from spike #604)

Tags; non-JSONata transformations (silently ignored); `*.Extension`, `*.ExtensionNotes`,
`Transformations.InputAttributesCount`, `Transformations.OutputAttributesCount`. Frontend
import/export buttons are #773.
