# ADR 0001: Field naming and source-standard normalization

Date: 2026-06-23

## Status
Proposed

> **Draft for team ratification.** This ADR records a conflict that has surfaced repeatedly but
> for which no decision is on record. The **Decision** below is a *recommendation* to react to and
> ratify (or revise) — not yet an accepted policy.

## Context

LIF has **two entry points** for outside input, with very different control points:

- **The MDR** — where schemas and mappings (transformations) are *defined*. This is authored and
  curated, so it *can* be guarded: the MDR can warn or refuse to accept a definition that downstream
  components cannot represent. **This ADR is about this entry point.**
- **The data** — learner records flowing through ingestion. We cannot dictate the shape of source
  data; the most we can do is validate it against its **assigned schema** and apply sanity checks.
  That data-vs-declared-type concern is a sibling problem (see *Scope* below and #1017).

At the MDR entry point, field/entity names come from external standards (CEDS, IMS, SIS/LMS exports,
…), and three pressures collide with **no recorded decision reconciling them**:

1. **Source standards / schema designers.** External standards deliver names verbatim — e.g. CEDS
   contributes `iSO639-2LangCode`, `iSO639-3LangCode`, `iSO639-5LangFamily` under `Person.Language`
   (hyphens, irregular capitalization). Designers reasonably want to preserve the source's identity.
2. **LIF naming convention** (`docs/specs/data-model-rules.md` → *Naming Styles*): entities/objects
   are PascalCase, scalar leaves are camelCase, enums are PascalCase — so a reader can tell
   containers from values at a glance.
3. **Technology constraints of the consumers** — and the same illegal name fails *differently* in
   each, because each consumer sanitizes differently (or not at all). An audit (code-verified where
   noted) found one bad name threatens multiple components:
   - **GraphQL** identifiers must match `/[_A-Za-z][_0-9A-Za-z]*/` — no hyphen, no leading digit, and
     `__` is reserved. A single illegal name fails the *entire* schema build (#1011; hardened in
     #1012). *Verified.*
   - **Semantic-search / MCP** builds Pydantic filter/mutation models from the **raw** schema names
     with no sanitization → an invalid identifier crashes the MCP server at startup (#1016).
     *Verified* (`semantic_search_service/core.py:129,134`).
   - **MongoDB** — update/insert keys are built from field names (`build_mongo_update_ops`,
     `query_cache_service/core.py:96-110`; `insert_one(model_dump(by_alias=True))`). A name starting
     with `$` is rejected by Mongo; a name containing `.` is misread as nesting → wrong/failed write.
     *Verified.*
   - **Composer / fragment paths** split path strings on `.` (`composer/core.py:60`; see ADR
     `composer/0002`) — a name that itself contains a `.` splits into spurious keys and the fragment
     is silently dropped. *Verified.*
   - **Python / Strawberry** attributes are snake_cased (`safe_identifier`).
   - **Query Planner** receives the GraphQL field names as `selected_fields` and matches them against
     the data-source keys — so a name sanitized in GraphQL but not in storage silently won't match.
   - **Translator / JSONata** — mapping expressions are **author-supplied** (`Transformation.Expression`),
     not auto-generated from names, so this is an *authoring hazard* rather than an automatic code
     failure: an unquoted hyphenated/spaced name parses as an operator expression. Mitigation belongs
     at the MDR boundary too — validate that a mapping expression compiles on write (see *Decision*).

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

**Scope.** This ADR covers the **MDR entry point** — the names and structure of *schema and mapping
definitions*, where the MDR can warn/restrict before a bad definition propagates. The related **data
entry point** — data that doesn't conform to its assigned type (e.g. a string for a field typed
`boolean`/`integer`/`date`, which the GraphQL resolver currently turns into a silent `null`) — is a
sibling concern tracked in #1017; the lever there is schema-conformance validation plus sanity checks
at ingestion, not name normalization. Both share the root theme (permissive input vs. strict
consumers), but they have different control points and warrant separate (if coordinated) decisions.

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
   into an unrepresentable state again. Mappings get the same treatment: a transformation expression
   is validated to **compile** (and to reference known elements) on write, so a malformed JSONata
   mapping is caught at authoring time rather than failing silently during translation.
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
- Validating at the MDR boundary makes the per-consumer crash guards redundant safety nets rather
  than the primary defense: the GraphQL hardening (#1012) and the still-needed semantic-search guard
  (#1016) stop being load-bearing once a bad name can't enter the model in the first place.
- Until the boundary check exists, **every** consumer that derives identifiers from schema names
  needs its own guard, and they will drift apart — exactly the inconsistency this decision removes.

## References
- Tracking issue: #1014 (this ADR + non-technical guide + enforcement)
- #1011 (GraphQL schema-build crash on `iSO639-2LangCode`), #1012 (codegen name hardening, incl. the
  `__`/collision edge cases)
- #1013 (rename the three `iSO639-*` CEDS language fields — first application of this policy)
- #1016 (semantic-search/MCP: same invalid-name crash, a different consumer — evidence this is not
  GraphQL-specific)
- #1018 (MongoDB: writes break on `$`/`.` field names — verified consumer-side failure)
- #1019 (Composer: dot-path split silently drops fragments for `.`-bearing names — verified)
- #1017 (sibling: data-vs-declared-type conformance — the *data* entry point)
- `docs/specs/data-model-rules.md` → *Naming Styles*
- Nygard, ["Documenting Architecture Decisions"](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
