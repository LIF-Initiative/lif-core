"""Write a portable file in canonical form (spec §9), so the same content always gives the same bytes.

Key order is the order the models declare their fields. NULL optional fields, and the optional
booleans when they are not true, are left out. Lists are sorted here by their keys, comparing strings
by Unicode code point, so the order a caller built them in does not matter.
"""

import json

from lif.mdr_portability.v1.models import CrosswalkFile, MappingGroupFile, Mapping, ModelFile, ValueSet

PortableFile = ModelFile | MappingGroupFile | CrosswalkFile


def dump_canonical(file: PortableFile) -> bytes:
    data = _sorted(file).model_dump(mode="json", exclude_defaults=True)
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _sorted(file: PortableFile) -> PortableFile:
    if isinstance(file, ModelFile):
        return file.model_copy(
            update={
                "ValueSets": sorted(
                    (_sorted_value_set(value_set) for value_set in file.ValueSets), key=lambda value_set: value_set.Name
                ),
                "Entities": sorted(file.Entities, key=lambda entity: entity.UniqueName),
                "Attributes": sorted(file.Attributes, key=lambda attribute: attribute.UniqueName),
                # Every parent is an entity, so a reference's (kind, key) order is its key order.
                "Associations": sorted(
                    file.Associations, key=lambda association: (association.Parent.Entity, association.Name)
                ),
            }
        )
    if isinstance(file, MappingGroupFile):
        return file.model_copy(
            update={
                "Mappings": sorted(
                    (_sorted_mapping(mapping) for mapping in file.Mappings), key=lambda mapping: mapping.Target.Path
                )
            }
        )
    return file.model_copy(update={"Entries": sorted(file.Entries, key=lambda entry: entry.Source)})


def _sorted_value_set(value_set: ValueSet) -> ValueSet:
    return value_set.model_copy(update={"Values": sorted(value_set.Values, key=lambda value: value.ValueName)})


def _sorted_mapping(mapping: Mapping) -> Mapping:
    return mapping.model_copy(update={"Sources": sorted(mapping.Sources, key=lambda source: source.Path)})
