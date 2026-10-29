"""Check the rules of a crosswalk file that span entries, refusing with the codes in Portability Spec §10.

parse_crosswalk_file checks each entry on its own. Resolving the value names in installed value sets
is the converter's job. Every rule is checked, and all the errors are raised together, as one
PortabilityErrorGroup.
"""

from collections import Counter
from collections.abc import Iterator

from lif.mdr_portability.errors import PortabilityError, PortabilityErrorCode, error_group
from lif.mdr_portability.v1.models import CrosswalkFile


def check_crosswalk_file(file: CrosswalkFile) -> None:
    errors = list(_check_for_duplicate_sources(file))
    if errors:
        raise error_group(errors)


def _check_for_duplicate_sources(file: CrosswalkFile) -> Iterator[PortabilityError]:
    # Each source value maps to exactly one target value (§7). Several sources may share a target.
    sources = Counter(entry.Source for entry in file.Entries)
    for source, count in sources.items():
        if count > 1:
            yield PortabilityError(
                PortabilityErrorCode.CROSSWALK_SOURCE_DUPLICATE,
                f"Entries[{source}]",
                f"{count} entries map this source",
            )
