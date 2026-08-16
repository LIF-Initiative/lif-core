from typing import List, Protocol
from lif.datatypes import IdentityMapping


class IdentityMapperStorage(Protocol):
    async def get_mapping_by_id(self, mapping_id: str) -> IdentityMapping | None:
        """
        Retrieve an identity mapping by its ID.
        Returns None if the mapping does not exist.
        """
        pass

    async def get_mappings(self, lif_organization_id: str, lif_organization_person_id: str) -> List[IdentityMapping]:
        """
        Retrieve identity mappings for a person in a LIF organization.
        """
        pass

    async def save_mapping(self, identity_mapping: IdentityMapping) -> IdentityMapping:
        """
        Save an identity mapping.
        If the mapping exists, update the existing mapping.
        Otherwise, create a new mapping.
        Returns the saved identity mapping.
        """
        pass

    async def save_mappings(self, identity_mappings: List[IdentityMapping]) -> List[IdentityMapping]:
        """
        Save a collection of identity mappings in a single transaction.

        If a mapping exists, update the existing mapping; otherwise, create a new one.
        Returns the saved identity mappings.
        """
        pass

    async def delete_mapping_by_id(self, mapping_id: str) -> IdentityMapping | None:
        """
        Delete the identity mapping identified by the mapping_id.
        Returns the deleted IdentityMapping, or None if it did not exist.
        """
