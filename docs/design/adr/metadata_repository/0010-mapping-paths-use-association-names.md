# ADR 0010: Mapping Paths Use Association Names

Date: 2026-10-13

## Status
Accepted

Amends [0009](0009-mapping-identity-and-cardinality.md) Decision 1 (how the target path is written) and defers 0009's update-in-place import.

## Context

[0009](0009-mapping-identity-and-cardinality.md) identifies a mapping by `(group, target path)`, and writes the target path as `EntityIdPath` with its numeric model prefixes removed. That leaves a chain of entity and attribute `UniqueName`s.

A chain of `UniqueName`s cannot tell roles apart. When the same child entity sits under one parent more than once, each time under a different relationship, every placement has the same path. Base LIF (model 1) has 8 such parent/child pairs in the seed, for example:

- `Course` → `Organization` as `accreditedBy` and as `approvedBy`;
- `Assessment` → `Organization` as `awardedBy` and as `offeredBy`;
- `Person.EmploymentLearningExperience` → `Organization` as `assertedBy`, `offeredBy` and `approvedBy`.

`Course.accreditedBy.name` and `Course.approvedBy.name` are different target fields, but under 0009 they have the same path, and so the same mapping identity.

The portable file format ([`mdr-portable-file-format.md`](../../../specs/mdr-portable-file-format.md), #1333) gives every association a required `Name`, the key the child appears under in its parent, which distinguishes the roles.

0009 also states that import updates an existing mapping in place when it has the same identity. The format's first version is create-only: import never changes existing rows.

## Decision

1. **A mapping path is a top-level entity, then association `Name`s.** The first segment is the `UniqueName` of an entity with no containing parent, in the group's source model for a source path, or its target model for the target path. Each later segment is the `Name` of an association under the previous entity, and the last segment reaches an attribute. Segments are separated by commas: `Course,AccreditedBy,name` (illustrative; a migrated model keeps today's keys, such as `accreditedByRefOrganization`). This replaces "`EntityIdPath` with its numeric model prefixes removed" in 0009 Decision 1. The rest of 0009 is unchanged: a mapping is still identified by `(group, target path)`, with one target per mapping and one mapping per target.
2. **Update-in-place is deferred.** The format's first version imports create-only. Recognizing an existing mapping by `(group, target path)` and updating it moves to the merge and replace import modes (NEW-J in the [portability plan](../../../operations/proposals/mdr-import-export-portability.md)).

## Alternatives

- **Keep `UniqueName` paths (0009 as written).** Simpler and closer to today's `EntityIdPath`, but two role placements of the same entity collapse to one identity, so the second mapping is refused as a shared target.
- **Add the relationship to `UniqueName` segments** (`Course.accreditedBy:Organization.name`). It distinguishes roles, but mixes two naming systems in one path, and the relationship is optional today (163 entity associations have none).
- **Implement update-in-place now.** Rejected for the format's first version. Create-only import is all or nothing and easy to verify, and update semantics belong with the merge and replace modes, which also need a preview (NEW-J).

## Consequences

- Paths match the keys records actually use, so every role is its own target field.
- Paths depend on association `Name`s. Renaming an association changes its paths, so 0009 Decision 5 (no renaming a field a mapping depends on) extends to association names.
- Today's `EntityIdPath` values must be converted. For each step, the association's `Name` comes from the migration rule in the format spec (§11, *Migration defaults*). All 10 live mapping paths in the seed start at a top-level entity.
- Until NEW-J lands, re-importing a changed group means importing it as a new group version.

## References

- #1333: portable file format
- #1223: MDR import/export portability
- [0009](0009-mapping-identity-and-cardinality.md): mapping identity and cardinality
- [`mdr-portable-file-format.md`](../../../specs/mdr-portable-file-format.md): §6.3 path format, Q3
- [Portability plan](../../../operations/proposals/mdr-import-export-portability.md): NEW-J
