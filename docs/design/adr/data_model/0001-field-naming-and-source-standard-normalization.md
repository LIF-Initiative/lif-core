# ADR 0001: Field naming and source-standard normalization

Date: 2026-06-23

## Status
Proposed

> **Draft for team ratification.** This ADR records a conflict that has surfaced repeatedly but
> for which no decision is on record. The **Decision** below is a *recommendation* to react to and
> ratify (or revise) — not yet an accepted policy.

## Context

LIF ingests field names from external standards and source systems (CEDS, IMS, SIS/LMS exports, …)
into the MDR, which is the runtime source of truth for the data model. Three naming pressures
collide, and there is **no recorded decision reconciling them**:

1. **Source standards / schema designers.** External standards deliver names verbatim — e.g. CEDS
   contributes `iSO639-2LangCode`, `iSO639-3LangCode`, `iSO639-5LangFamily` under `Person.Language`
   (hyphens, irregular capitalization). Designers reasonably want to preserve the source's identity.
2. **LIF naming convention** (`docs/specs/data-model-rules.md` → *Naming Styles*): entities/objects
   are PascalCase, scalar leaves are camelCase, enums are PascalCase — so a reader can tell
   containers from values at a glance.
3. **Technology constraints of the consumers:**
   - **GraphQL** identifiers must match `/[_A-Za-z][_0-9A-Za-z]*/` — no hyphens, no leading digit.
     A single illegal name fails the *entire* schema build.
   - **Python / Strawberry** attributes are snake_cased (`safe_identifier`).
   - **Query Planner** receives the GraphQL field names as `selected_fields` and matches them
     against the data source's keys.
   - **JSON / MongoDB** store names verbatim; the **translator** relies on case-insensitive lookups.

The convention is documented but, per `data-model-rules.md`, "enforced by readers, not tooling."
That gap let `iSO639-2LangCode` reach the MDR and **crash GraphQL schema generation in both dev and
demo** (#1011) — the service crash-looped (`0/1`, `503`). Code hardening (#1012) now sanitizes names
so a bad one can no longer crash the build, but a sanitized-but-unnormalized field is
**name-inconsistent across layers** (GraphQL `iSO639_2LangCode` vs. the Query Planner / data-source
key `iSO639-2LangCode` vs. the dataclass attr `i_so639_2_lang_code`) and therefore returns null —
it never round-trips data. So sanitization alone does not make such a field usable.

This is the same class of conflict teams hit elsewhere (e.g. Clojure's kebab-case idiom vs. JSON /
DynamoDB expectations): a **domain/source naming idiom vs. technology/serialization idioms**, with no
single representation that satisfies everyone.

## Decision

*(Recommended — pending ratification.)* Treat the **MDR write boundary** as the place where LIF
naming is guaranteed, rather than relying on every downstream consumer to cope with arbitrary names:

1. **Canonical LIF name, normalized on intake.** Every element gets a canonical name that obeys the
   LIF convention and is a valid identifier for all consumers: scalars camelCase, entities/enums
   PascalCase, restricted to `[A-Za-z0-9]`, not leading with a digit. Source names that violate this
   are normalized (e.g. `iSO639-2LangCode` → `iso6392LangCode`).
2. **Preserve the source name as metadata, not as the identifier.** Keep the original
   standard's spelling (and its standard, e.g. "CEDS") in a descriptive/provenance field so nothing
   is lost (consistent with the "no loss" principle) — but it is never used as the GraphQL/Query/
   storage key.
3. **Enforce at write time.** The MDR API validates names on create/update and rejects (or
   auto-normalizes with a warning) anything that violates the convention, so the model cannot drift
   into an unrepresentable state again.
4. **Keep codegen sanitization (#1012) as defense-in-depth** — a backstop so a bad name degrades a
   single field instead of taking down the whole service, never the primary guarantee.

Also produce a **non-technical naming guide** for schema designers/contributors, and **lint** the
checked-in convention files (`reference_data/schemas/lif-schema.json`, seed SQL, `.graphql`,
`information_sources_config*.yml`, sample data).

## Alternatives

- **Status quo — convention enforced by readers only.** Rejected: it already failed in production
  (#1011); nothing prevents the next illegal name.
- **Codegen sanitization only (#1012), no naming policy.** Rejected as the *sole* fix: it stops the
  crash but leaves the offending fields non-functional (name diverges across GraphQL / Query Planner
  / storage) and masks the underlying data-model problem.
- **Allow arbitrary source names; make every consumer sanitize consistently.** Rejected: each
  technology sanitizes differently (GraphQL vs. Python vs. storage), so the same field ends up with
  different keys per layer — exactly the round-trip failure seen here. Centralizing at the MDR
  boundary avoids N inconsistent transforms.
- **Use the source name as the identifier and quote/escape it everywhere.** Rejected: GraphQL has no
  escape for illegal identifier characters, so this is not even possible for GraphQL consumers.

## Consequences

- A canonical-name + source-name-metadata model must be defined and added to the MDR (data + API
  validation). Existing violations need a one-time migration — tracked in #1013 (the three
  `iSO639-*` fields), which becomes the first application of this policy.
- Adopters extending their Org LIF get guardrails (clear errors at write time) instead of a crashed
  GraphQL service.
- Provenance is preserved (source name retained as metadata), satisfying "no loss."
- New work: MDR write-time validation/normalization, lint for the convention files, and the
  non-technical guide. Some short-term effort; large long-term reduction in naming-drift incidents.
- #1012 remains as a safety net regardless of which option is ratified.

## References
- Tracking issue: #1014 (this ADR + non-technical guide + enforcement)
- #1011 (GraphQL schema-build crash on `iSO639-2LangCode`), #1012 (codegen name hardening)
- #1013 (rename the three `iSO639-*` CEDS language fields — first application of this policy)
- `docs/specs/data-model-rules.md` → *Naming Styles*
- Nygard, ["Documenting Architecture Decisions"](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
