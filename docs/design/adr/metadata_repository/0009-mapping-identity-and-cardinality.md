# ADR 0009: Mapping Identity and Cardinality

Date: 2026-09-30

## Status
Accepted

Amends [0008](0008-data-model-use-cases.md) (the *Transformations / Mappings* section's "many-to-many" statement).

## Context

A mapping (a transformation) has no portable identity. Exports identify it, and everything it touches, by database ID (`Id`, `TransformationGroupId`, `AttributeId`, `EntityId`), so an exported group can only be matched back to rows in the install that produced it. Import needs a way to recognize "the same mapping" in another install, so it can update rather than duplicate or delete.

Three candidates were weighed in #1315 (Decision 3):

- **The mapping's name.** Not unique within a group, and editable, so not an identity.
- **A generated key** (`PortableKey`: a UUID minted once, written into exports, preserved on import).
- **What the mapping produces:** its target path, within its group.

Evidence gathered for the decision:

- Across the three versioned transformation groups in `reference_data/transformations/` (185 mappings), every well-formed mapping has a distinct target within its group. The only collisions are two mappings that declare no target at all, the two rules behind the malformed export in #1144.
- The #1296 test group (56 rules, written to exercise combines, merges and de-duplication) has one target per rule and no shared targets. 13 of its rules read several sources.
- Across the full seed history, 1 of 1,378 mappings ever declared two targets, and it is soft-deleted. No live mapping has more than one.
- Import already saves every declared source attribute, one row per source.
- Renaming an attribute in place silently breaks the mappings that use it: the stored `EntityIdPath` and the JSONata expression keep the old name (#1338).

## Decision

1. **A mapping is identified by `(group, target path)`.** A group is identified by its source model, target model and version, and a model by its name, version and contributor organization, the identities [0008](0008-data-model-use-cases.md) already requires to be unique. The target path is name-based: `EntityIdPath` with its numeric model prefixes removed.
2. **Within a group, mappings and target fields correspond one-to-one.** Every mapping declares **exactly one** target field, and **no target field is produced by more than one mapping**.
3. **Sources are content, not identity.** A mapping may read several source fields. They are a set, and the declared set must list **every** field the expression reads, fallbacks included. JSONata expresses fallbacks within one mapping (`??`, `?:`, `$exists()`).
4. **An expression must write only its declared target.** Writing anything else is a validation error.
5. **A field that a mapping depends on cannot be renamed in place.** The rename is refused and lists the dependent mappings. A rename goes through a new schema version or an explicit re-point of those mappings.

Editing a mapping's sources, expression or notes keeps its identity, so import updates it in place. Changing its target produces a different mapping.

## Alternatives

- **Generated key (`PortableKey`).** Its one real advantage is surviving an in-place rename of the target. Rejected: Decision 5 blocks such renames, and the key is opaque in files and diffs, must be invented for hand-written files, and would let two mappings silently write the same field.
- **Identity as a set of targets.** Would allow one mapping to write several fields. Rejected: adding a field to an expression would change the mapping's identity, and undeclared writes, the #1144 failure, would stay possible.
- **Mapping names.** Rejected: not unique, and editable.

## Consequences

- [0008](0008-data-model-use-cases.md)'s "many-to-many" statement is narrowed. **Several sources feeding one mapping: yes.** One source field feeding several mappings: yes. **Several mappings producing the same target field: no.**
- Create, update and import must enforce the one-to-one rule and the declared-target check. The two target-less rules in the CLR group would be rejected and must be fixed or removed.
- Exported mapping files become readable and easy to diff meaningfully, and hand-written files need no keys.
- Renaming a mapped field requires a version or a re-point, which also closes #1338's silent breakage.
- No schema migration is needed for identity (no new key column).

## References

- #1223: MDR import/export portability
- #1315: implementation plan (Decision 3)
- #1144: undeclared target writes producing a near-empty export
- #1296: the Sample LDE Target Test group
- #1338: renaming or deleting an attribute silently breaks or deletes its mappings
- [0008](0008-data-model-use-cases.md): MDR data model use cases
