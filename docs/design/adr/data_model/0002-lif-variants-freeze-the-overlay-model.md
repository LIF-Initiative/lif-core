# ADR 0002: LIF Variants — Freeze the Overlay Model; a Variant Becomes a Source Schema Plus a Mapping

Date: 2026-09-30

## Status
Superseded by [data_model/0004](0004-retire-overlays-variants-as-copies.md), which retires the overlay model rather than freezing it.

Amends [metadata_repository/0008](../metadata_repository/0008-data-model-use-cases.md) (the *Org LIF* and *Partner LIF* sections).

## Context

MDR lets a deployer differ from Base LIF through an **overlay**: an *Org LIF* includes Base LIF entities and attributes (inclusions) and adds its own (extensions), and a *Partner LIF* is another system's Org LIF imported read-only ([metadata_repository/0008](../metadata_repository/0008-data-model-use-cases.md)). The intent was flexibility: small differences between deployers without losing compatibility.

The overlay has become the most expensive part of the data model to carry:

- **Code keyed on type names breaks for the types it forgot.** The base-model lookup filters on `Type == "OrgLIF"`, so every *Partner LIF* export, and `GET /datamodels/base/{id}`, fails with a 500 (#1321).
- **It adds rules nothing else needs.** Of MDR's eight uniqueness rules, the only one that exists solely for overlays is `EntityAttributeAssociation.ExtendedByDataModelId`. The other seven protect things any model has.
- **Portability has to preserve it.** A lossless export of an Org LIF must keep owned vs. inherited vs. overriding for every element, across the ancestor chain (#1315, Decision 5).
- **It inverts MDR's own purpose.** MDR exists to map many source formats into one target model. A deployer's variant of LIF is the one format it does not map; it layers the variant on top instead.

## Decision

1. **Freeze the overlay model.** No new investment in extensions or inclusions. Live defects in the existing behavior (such as #1321) are still fixed.
2. **Keep ancestor-chain work local.** Where import/export must walk an Org LIF's chain, it does so inside import/export (#1315 option 5b), rather than extending full-chain traversal to every service (option 5a).
3. **Direction: a LIF variant is a Source Schema plus a mapping to the target LIF.** A deployer's variant, and a partner's, is modeled like any other source format: a self-contained *Source Schema* with a transformation group to the target LIF. Differences between deployers become mappings, which MDR already versions, exports and translates.

What this does **not** change: sharing *within* a model. Base LIF has entities that appear under many parents (30 have more than one; `CredentialAward` has seven) and entities that reference each other. That needs references whatever happens to overlays; see [data_model/0003](0003-references-between-shared-entities.md).

## Alternatives

- **Keep the overlay model and invest in it.** Implement full-chain traversal everywhere (one shared helper with a cycle guard, touching `valueset_service`, `transformation_service` and both name-lookup helpers). Rejected: it deepens the model this ADR concludes should be replaced, and each new caller is another place for type-name defects like #1321.
- **Replace the overlay model now.** The right end state, but it needs a new import path for variants and a migration of existing Org LIF and Partner LIF content into Source Schemas and mappings. Rejected for now on cost; it is the recorded direction.

## Consequences

- The *Org LIF* and *Partner LIF* sections of [metadata_repository/0008](../metadata_repository/0008-data-model-use-cases.md) describe behavior that is **frozen, not extended**. New features should not build on inclusions or extensions.
- A future migration must convert each existing Org LIF and Partner LIF into a Source Schema and a transformation group, preserving the content the overlay currently expresses.
- Every model becomes self-contained, which simplifies portability (no ownership across models to preserve) and removes the strongest argument against storing models as documents (#1132).
- Until the migration, both mechanisms coexist; import/export must still handle existing overlays correctly.

## References

- #1223: MDR import/export portability
- #1315: implementation plan (Decision 5)
- #1321: Partner LIF export and base-model lookup failure
- #1132: MDR storage
- [metadata_repository/0008](../metadata_repository/0008-data-model-use-cases.md): MDR data model use cases
- [metadata_repository/0009](../metadata_repository/0009-mapping-identity-and-cardinality.md): mapping identity
- [data_model/0003](0003-references-between-shared-entities.md): references between shared entities
