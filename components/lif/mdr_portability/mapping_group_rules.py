"""Check the rules of a mapping-group file that span mappings, refusing with the codes in Portability Spec §10.

parse_mapping_group_file checks each object on its own, including a mapping's single target and its
expression language. These rules compare mappings and paths with each other, and need no installed
model: resolving each path in a model is mapping_paths' job. Every rule is checked, and all the errors
are raised together, as one PortabilityErrorGroup.
"""

from collections import Counter
from collections.abc import Iterator

from lif.mdr_portability.errors import PortabilityError, PortabilityErrorCode, PortabilityErrorGroup
from lif.mdr_portability.mapping_paths import check_path_syntax
from lif.mdr_portability.v1.models import MappingGroupFile


def check_mapping_group_file(file: MappingGroupFile) -> None:
    errors = [*_check_for_shared_targets(file), *_check_for_duplicate_sources(file), *_check_path_syntax(file)]
    if errors:
        raise PortabilityErrorGroup(f"{len(errors)} portability error{'s' if len(errors) != 1 else ''}", errors)


def _check_for_shared_targets(file: MappingGroupFile) -> Iterator[PortabilityError]:
    # A mapping is identified by (group, target path), so no two mappings may write the same target
    # (§6.2, ADR metadata_repository/0009).
    targets = Counter(mapping.Target.Path for mapping in file.Mappings)
    for path, count in targets.items():
        if count > 1:
            yield PortabilityError(
                PortabilityErrorCode.MAPPING_TARGET_SHARED, f"Mappings[{path}]", f"{count} mappings write this target"
            )


def _check_for_duplicate_sources(file: MappingGroupFile) -> Iterator[PortabilityError]:
    # A mapping lists each source path once (§6.2).
    for mapping in file.Mappings:
        sources = Counter(source.Path for source in mapping.Sources)
        for path, count in sources.items():
            if count > 1:
                yield PortabilityError(
                    PortabilityErrorCode.DUPLICATE_KEY,
                    f"Mappings[{mapping.Target.Path}].Sources[{path}]",
                    f"{count} sources share the path {path!r}",
                )


def _check_path_syntax(file: MappingGroupFile) -> Iterator[PortabilityError]:
    for mapping in file.Mappings:
        mapping_element = f"Mappings[{mapping.Target.Path}]"
        yield from check_path_syntax(mapping.Target.Path, f"{mapping_element}.Target.Path")
        for source in mapping.Sources:
            yield from check_path_syntax(source.Path, f"{mapping_element}.Sources[{source.Path}].Path")
