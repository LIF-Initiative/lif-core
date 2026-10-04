# ADR 0003: References Between Shared Entities

Date: 2026-09-30

## Status
Accepted

This records the direction. Implementation is future work, except the explicit schema-level reference marker (#1026), which lossless round trips already require.

## Context

The standards LIF models (CEDS, Open Badges 3, CLR v2, Ed-Fi) are trees on the page, but some things in them belong in more than one place. Mature standards handle that the same way: the shared thing gets a declared identity, and every other place refers to it. OpenAPI uses `$ref`; Open Badges 3 and CLR v2 use JSON-LD `@id`; Ed-Fi uses reference objects built from natural keys.

**The principle this ADR adopts: a reference is part of the data model and of its output, never an artifact of how the data is stored.** Database row IDs are not references.

LIF falls short of that at two levels.

**Schema level (MDR model documents).** Base LIF shares entities across parents: 30 entities have more than one parent (`CredentialAward` has seven), and the learning-experience entities reference each other. MDR's schema generator inlines every `$ref` and records a reference only by naming a property `<relationship>Ref<Type>`, so references are lost or guessed on a round trip (#1026, #1062).

**Instance level (learner records).** The LIF schema has reference properties (`issuedByRefOrganization`, `offeredByRefOrganization`, and others), but each is an inline object with no canonical key. In one demo record (`projects/mongodb/sample_data/advisor-demo-org3/Alan-validated.json`, 119 KB), the same institution is referenced about 25 times, keyed three incompatible ways: by an `identifier`, by `"State University SIS"`, and by `"stateu-state-university-id"`. No consumer can reliably tell these are the same institution.

## Decision

1. **Schema level: references are explicit.** Exports carry `$ref`, or an explicit reference marker, rather than a naming convention, and a round trip preserves relationship names (#1026, #1062).
2. **Instance level: full JSON-LD.** Referenced nodes carry an `@id` (an IRI), references are made by `@id`, and records carry an `@context`. The pipeline adopts JSON-LD processing (expansion, flattening, framing), which de-duplicates nodes by `@id` and reshapes a flat graph into whatever tree a consumer needs.
3. **Organization identifiers are layered.** Use an authoritative external identifier where one exists (IPEDS or OPEID for postsecondary institutions, NCES for K-12), written as `(identificationSystem, identifier)`. Use `did:web` where an issuer publishes one. Otherwise, a LIF organization registry mints an IRI.
4. **A reference carries the key, plus a copy only of attested fields.** Details that were part of what was attested at the time, such as the issuer name as printed on an award, are kept with the reference because they are historical facts. Everything else resolves through the reference.
5. **Provenance stays on each node.** `informationSourceOrganization` remains a per-node value.

## Alternatives

- **JSON-LD identity conventions only** (IRI ids and `{id}` references, without the processing stack). Lower cost now, and compatible with adding processing later. Rejected in favor of the standard de-duplication and framing that full JSON-LD provides.
- **A LIF registry for every organization identifier.** One consistent scheme, but every deployment would depend on the registry, and external systems would still need a crosswalk.
- **`did:web` only.** Aligned with how Open Badges 3 issuers are identified, but most institutions in current data do not publish one.
- **Key-only references.** Cleanest, but loses the historical truth of what an award stated when an institution is later renamed or merged.
- **Full copies, as today.** No resolution needed, but duplication and drift remain, as the three keys for one institution show.
- **Provenance once per fragment.** Would remove most of the per-node copies (311 in the record above). Not adopted; provenance stays per node.

## Consequences

- The pipeline needs a JSON-LD processor, and `@context` documents must be pinned and served locally rather than fetched at runtime. The current JSONata, GraphQL and MongoDB layers do not resolve `@id` references themselves.
- An organization registry, or an equivalent crosswalk, is required. Nothing like it exists today; people have the Identity Mapper, organizations have no counterpart. References only resolve if every source uses the same key for the same organization.
- Referential integrity becomes a data-model rule, checkable by a validator on any storage engine: every referenced node has a unique `@id`, and every reference resolves.
- LIF's output aligns with the JSON-LD formats at its edges (Open Badges 3, CLR v2), which require `@context`.
- Records stay larger than a per-fragment provenance design would make them.

## References

- #1026: explicit export marker for references
- #1062: relationship names dropped on reference export
- #1223: MDR import/export portability
- #808: Organization as a queryable root entity
- #689: unroll non-person references into Person responses
- [data_model/0002](0002-lif-variants-freeze-the-overlay-model.md): LIF variants
- [JSON-LD 1.1](https://www.w3.org/TR/json-ld11/)
