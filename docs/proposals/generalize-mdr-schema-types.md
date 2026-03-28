# Option A: Generalize MDR Schema Types (Preserve Inheritance Model)

**Date:** 2026-02-19
**Status:** Draft — discussion only

---

## Summary

Rename and generalize the existing LIF-specific type hierarchy while preserving the base/derived/partner inheritance model. This approach keeps the extension and inclusion mechanics but removes the LIF branding so any standard can serve as a base schema.

| Current | Proposed |
|---------|----------|
| `BaseLIF` | `BaseSchema` |
| `OrgLIF` | `DerivedSchema` |
| `PartnerLIF` | `PartnerSchema` |
| `SourceSchema` | `SourceSchema` |

---

## Effort Estimate (AI-assisted)

| Area | Estimated Hours |
|------|----------------|
| Database migration (rename enum, migrate data) | 4–6 |
| API — type system & services | 8–12 |
| API — endpoints | 4–6 |
| Frontend — routing & constants | 6–8 |
| Frontend — tree & model explorer | 8–12 |
| Frontend — services & API calls | 4–6 |
| Testing | 8–12 |
| Documentation | 2–4 |
| **Total** | **44–66 hours** |

Without AI assistance, expect roughly 2–3x these numbers.

---

## Risks

- **Backward compatibility**: Existing deployments have `BaseLIF`/`OrgLIF`/`PartnerLIF` in their databases. Migration must be seamless.
- **Seed data**: Any seed data or scripts referencing LIF types by name need updating.
- **Downstream consumers**: Services that read `DataModelType` from the MDR API (query planner, translator, GraphQL) may need updates.
- **Scope creep**: Generalizing types is one thing; actually supporting multiple concurrent base schemas with cross-standard translation is a larger architectural change that may surface additional work beyond this estimate.
