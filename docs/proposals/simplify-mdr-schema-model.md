# Option B: Simplify MDR to Flat Schema Model (Remove Inheritance)

**Date:** 2026-02-19
**Status:** Draft — discussion only

---

## Summary

Rather than generalizing the existing base/derived/partner inheritance hierarchy, remove it entirely. The MDR becomes a registry of schemas (standards) that can be browsed, explored, and mapped between — with no special type distinctions or extension mechanics.

The core ask: **capture, navigate, and explore any standard, and define mappings between them.**

---

## Proposed Model

### Before (4 types with inheritance)

```
BaseLIF ──┬── OrgLIF (extends BaseLIF, tracks inclusions)
          └── PartnerLIF (extends BaseLIF, tracks inclusions)
SourceSchema (standalone, no inheritance)
```

### After (1 type, flat)

```
Schema (any standard: LIF, CTDL, Ed-Fi, CASE, org-specific, etc.)
  └── Mappings between schemas define field-level relationships
```

All schemas are peers. LIF is just another schema in the registry, not a privileged base type.

---

## What Gets Removed

| Current Concept | Disposition |
|----------------|-------------|
| `DataModelType` enum (BaseLIF/OrgLIF/PartnerLIF/SourceSchema) | Replace with a single type or remove entirely |
| `BaseDataModelId` foreign key | Remove — no parent/child schema relationship |
| `ExtInclusionsFromBaseDM` table | Remove — no inclusion tracking needed |
| `ExtendedByDataModelId` on EntityAssociation / EntityAttributeAssociation | Remove — no extension tracking |
| `ContributorOrganization` filtering ("LIF" vs org vs partner) | Remove — schemas are standalone |
| `partner_only` / `org_ext_only` / `public_only` filter modes | Remove from API and UI |
| BaseLIF deletion protection | Remove — all schemas are deletable (or use a generic "locked" flag) |
| Hardcoded `data_model_id=1` | Remove |
| `/is_orglif/`, `/orglif/`, `/base/` endpoints | Remove |
| Dedicated "LIF Model" and "Data Extensions" UI pages | Replace with a unified schema explorer |
| OrgLIF sub-views (All, Base Inclusions, Public, Extensions, Partner) | Remove — single view per schema |
| Extension/partner classification in tree explorer | Remove |

---

## What Gets Added or Changed

### API
- **Schema CRUD** simplifies — create, read, update, delete any schema with no type-specific validation
- **Mappings** become the primary relationship between schemas (this already partially exists in the Mappings feature)
- Optional metadata fields on schemas: `standard_name`, `version`, `organization` for categorization without hard type distinctions
- Endpoints simplify to standard REST for schemas, entities, attributes, and mappings

### Frontend
- **Unified schema explorer** — single tree/list of all schemas, no folder grouping by type
- **Schema detail view** — browse entities and attributes for any schema, no inclusion/extension overlays
- **Mappings view** — already exists, becomes the primary way to relate schemas to each other
- Simpler tree component — no type-based branching, color coding, or sub-views

### Database
- Migration to drop or ignore `DataModelType`, `BaseDataModelId`, `ExtInclusionsFromBaseDM`, and extension tracking columns
- Existing data preserved (BaseLIF becomes just a schema named "LIF")

---

## Work Breakdown

### 1. Database Migration
- Drop or deprecate `DataModelType` column (or migrate all values to a single type)
- Drop `BaseDataModelId` foreign key
- Drop `ExtInclusionsFromBaseDM` table
- Drop `ExtendedByDataModelId` from association tables
- Add optional metadata columns if needed (`standard_name`, `version`)
- **Estimate: 3–5 hours**

### 2. API — Remove Inheritance Logic
- Remove `DataModelType` enum or collapse to single value
- Remove all type-specific validation in `datamodel_service.py`
- Remove extension/inclusion filtering in `entity_service.py` and `attribute_service.py`
- Remove base model chain traversal in `jinja_helper_service.py`
- Remove auto-extension marking in entity creation
- **Estimate: 6–8 hours**

### 3. API — Simplify Endpoints
- Remove `/is_orglif/`, `/orglif/`, `/base/` endpoints
- Remove `partner_only`, `org_ext_only`, `public_only` parameters from `/with_details/`
- Remove hardcoded `data_model_id=1` defaults
- Remove or simplify inclusions endpoints
- **Estimate: 3–4 hours**

### 4. Frontend — Simplify Schema Explorer
- Remove type constants and type-based routing
- Replace `/explore/lif-model` and data-extensions pages with unified schema list
- Simplify `DataModelSelector.tsx` — no type-based auto-navigation or defaults
- Simplify `SimpleTree.tsx` — flat list of schemas, no type-based folders
- **Estimate: 6–8 hours**

### 5. Frontend — Simplify Model Explorer
- Remove BaseLIF base-data fetching logic
- Remove inclusion/visibility toggles
- Remove extension/partner classification in `TreeModelExplorer.tsx`
- Simplify to: browse entities and attributes for a single schema
- **Estimate: 4–6 hours**

### 6. Frontend — Services & API Calls
- Remove `listOrgLifModels()` and type-specific service functions
- Simplify `CreateDataModelParams` — no type restrictions
- Remove inclusion-related API calls
- **Estimate: 2–4 hours**

### 7. Testing
- Remove/update tests for deleted functionality
- Add tests for simplified schema CRUD
- Verify mappings still work correctly
- Integration test updates
- **Estimate: 6–8 hours**

### 8. Documentation
- Update CLAUDE.md and API docs
- Migration guide for existing deployments
- **Estimate: 2–3 hours**

---

## Effort Summary

| Area | Estimated Hours |
|------|----------------|
| Database migration | 3–5 |
| API — remove inheritance logic | 6–8 |
| API — simplify endpoints | 3–4 |
| Frontend — simplify schema explorer | 6–8 |
| Frontend — simplify model explorer | 4–6 |
| Frontend — services & API calls | 2–4 |
| Testing | 6–8 |
| Documentation | 2–3 |
| **Total** | **32–46 hours** |

These estimates assume AI-assisted development. Without AI assistance, expect roughly 2–3x.

---

## Comparison with Option A (Generalize Types)

| | Option A: Generalize | Option B: Simplify |
|---|---|---|
| **Approach** | Rename types, keep inheritance | Remove types and inheritance |
| **Estimate** | 44–66 hours | 32–46 hours |
| **Complexity after** | Same as today, different names | Significantly reduced |
| **Extensible schemas** | Yes | No — by design |
| **Multi-standard support** | Requires additional design | Natural — all schemas are peers |
| **Risk** | Medium — rename across full stack | Medium — removing features has fewer edge cases than renaming them |
| **Migration** | Rename in place | Drop columns/tables, existing data becomes flat |

---

## Risks & Considerations

- **Loss of extension capability**: If org-specific or partner extensions are needed in the future, they would need to be re-implemented. Confirm with stakeholders that flat schemas meet the need.
- **Existing OrgLIF/PartnerLIF data**: Any deployments with OrgLIF or PartnerLIF schemas need a migration path. Extended entities/attributes would become standalone entries in the base schema or be dropped.
- **Mappings feature maturity**: The existing Mappings view becomes the primary way to relate schemas. Verify it is robust enough for the cross-standard use case.
- **Downstream services**: Query planner, translator, and GraphQL services may reference `DataModelType`. Audit for impact.
