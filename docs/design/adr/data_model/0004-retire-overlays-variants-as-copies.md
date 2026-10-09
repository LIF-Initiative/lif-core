# ADR 0004: Retire the Overlay Model; Variants Are Self-Contained Copies, Compared by Diff

Date: 2026-10-09

## Status
Accepted

Supersedes [data_model/0002](0002-lif-variants-freeze-the-overlay-model.md). 

Amends [metadata_repository/0008](../metadata_repository/0008-data-model-use-cases.md) (retires the four model types and their "number supported" limits, and the `Inclusions` check on mapping paths).

This records the direction. Implementation is future work.

## Context

Overlays were built for a central ecosystem: one official LIF model under central control, which implementers extend (extensions) or narrow (inclusions), and share with each other ([metadata_repository/0008](../metadata_repository/0008-data-model-use-cases.md)). That ecosystem will not exist. LIF is open source with no central service. At most, a district publishes its version of the model and schools adopt it or not, with no hard link between the systems.

What adopters actually do is collect learner data from many upstream sources into one record per learner, then share that record downstream. MDR's job is mapping many models into one target, and adopters also want to map into targets other than LIF.

[data_model/0002](0002-lif-variants-freeze-the-overlay-model.md) froze overlays because they are the most expensive part of the data model to carry: type-name checks that break for the types they forget (#1321), uniqueness rules that exist only for overlays, and an ancestor chain every export has to preserve (#1315). Freezing kept that cost in place. Every live overlay is one level deep, and no source schema was ever extended, so the depth the model supports is unused.

Discussion [#1367](https://github.com/orgs/LIF-Initiative/discussions/1367) proposed replacing the four model types with layered models of any depth. The team chose to simplify even further.

## Decision

1. **One kind of model, and every model is self-contained.** The *Base LIF*, *Org LIF*, *Partner LIF* and *Source Schema* distinctions go away. A model does not inherit from or include another model.
2. **Overlays are retired.** No new Org LIF or Partner LIF models, inclusions or extensions. Existing overlay models are converted once into self-contained models that produce the same schema they produce today.
3. **A variant is a copy.** Cloning a model copies everything it shows, including what it inherited, into one model that stands alone. The copy is then edited freely; nothing restricts which ways it may differ from its source.
4. **Schema diff explains how two models differ.** It matches by name and path, never database ID, so it works on copies and on imported files. It reports entities, attributes, value sets, values and associations that were added, removed or changed, including their flags.
5. **Lineage, not inheritance.** A copy records what it was copied from as one portable key: the source model's name, version and contributor organization. Diff uses it as the default comparison. Lineage carries no behavior; deleting or changing the source does not affect the copy.
6. **Services name a model by its portable key, not a database ID.** Services that load a model from MDR identify it by name, version and contributor organization, resolved by MDR. (Today they are configured with `OPENAPI_DATA_MODEL_ID`, which defaults to `17` in the docker-compose files.)

A variant can still be expressed the way 0002 proposed, as a separate model plus a mapping into the official target. That remains valid when the adopter wants to keep the official target unchanged; diff shows which approach is cheaper.

What this does **not** change: references within a model ([data_model/0003](0003-references-between-shared-entities.md)).

## Alternatives

- **Keep the freeze (0002).** No migration risk, but the overlay code paths, their type-name defects, and the ancestor chain in every export stay indefinitely, for a use no one has.
- **Layered models to any depth (#1367).** One kind of model, with each layer inheriting from its parent and flags that can only narrow. Rejected: it keeps inheritance, and with it the ancestor chain, for depth that is not used.
- **A variant is always a Source Schema plus a mapping (0002's direction).** Keeps the official target fixed, but an adopter who wants to change their own target model has to map rather than edit it. Kept as one option (above), not the only one.

## Consequences

- Every model is self-contained, so the portable file format (#1333) holds one model with an optional lineage key.
- Clone must produce a complete, self-contained copy. Today it keeps the overlay link and does not copy inherited content.
- Diff is new work, and its rules for recognizing renamed or moved elements are not yet designed.
- Lineage needs a database migration, and a merged migration must actually be applied to every environment and tenant schema (#1226).
- Converting the model every running service loads carries the most risk. The pass criterion is that MDR generates the same schema for it before and after conversion.
- Adopters lose the guarantee that a variant only narrows its source. Diff makes the difference visible but does not prevent it.
- Changes to a source model no longer flow into its copies. Adopters re-clone or apply the changes by hand, guided by diff.
- Overlay code paths can stay in place, unused, until no overlay models remain and none can be created, then be removed.

## References

- Discussion [#1367](https://github.com/orgs/LIF-Initiative/discussions/1367): simplify the MDR data model
- #1223: MDR import/export portability
- #1333: portable file format and converter
- #1315: portability implementation plan
- #1321: Partner LIF export and base-model lookup failure
- #1226: merged migrations that never reach a database
- [data_model/0002](0002-lif-variants-freeze-the-overlay-model.md): freeze the overlay model (superseded)
- [data_model/0003](0003-references-between-shared-entities.md): references between shared entities
- [metadata_repository/0008](../metadata_repository/0008-data-model-use-cases.md): MDR data model use cases
