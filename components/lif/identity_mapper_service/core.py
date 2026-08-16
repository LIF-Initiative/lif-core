from typing import List

from lif.datatypes import IdentityMapping
from lif.exceptions.core import DataNotFoundException
from lif.identity_mapper_storage.core import IdentityMapperStorage
from lif.exceptions.core import DataStoreException


class IdentityMapperService:
    def __init__(self, storage: IdentityMapperStorage):
        self.storage = storage

    async def get_mappings(self, lif_organization_id: str, lif_organization_person_id: str) -> List[IdentityMapping]:
        """
        Retrieve identity mappings for a person in a LIF organization.

        Args:
            lif_organization_id (str): LIF organization ID.
            lif_organization_person_id (str): LIF organization person ID.

        Returns:
            List[IdentityMapping]: List of identity mappings.

        Raises:
            ValueError: If the input data is invalid.
            DataStoreException: If there is an error retrieving the mappings.
        """
        if not lif_organization_id or not lif_organization_person_id:
            raise ValueError("Invalid input data for retrieving mappings")

        return await self.storage.get_mappings(lif_organization_id, lif_organization_person_id)

    async def save_mappings(
        self, lif_organization_id: str, lif_organization_person_id: str, mappings: List[IdentityMapping]
    ) -> List[IdentityMapping]:
        """
        Save identity mappings for a person in a LIF organization.

        Args:
            lif_organization_id (str): LIF organization ID.
            lif_organization_person_id (str): LIF organization person ID.
            mappings (List[IdentityMapping]): List of identity mappings to save.

        Raises:
            ValueError: If the input data is invalid.
        """
        if not lif_organization_id or not lif_organization_person_id or not mappings:
            raise ValueError("Invalid input data for saving mappings")

        for mapping in mappings:
            if lif_organization_id != mapping.lif_organization_id:
                raise ValueError("LIF organization ID in mapping does not match the provided LIF organization ID")
            if lif_organization_person_id != mapping.lif_organization_person_id:
                raise ValueError(
                    "LIF organization person ID in mapping does not match the provided LIF organization person ID"
                )

        saved_mappings: List[IdentityMapping] = await self.storage.save_mappings(mappings)
        if not saved_mappings:
            raise DataStoreException("Failed to save mappings")
        return saved_mappings

    async def delete_mapping(self, lif_organization_id: str, lif_organization_person_id: str, mapping_id: str) -> None:
        """
        Delete an identity mapping for a person in a LIF organization.

        Args:
            lif_organization_id (str): LIF organization ID.
            lif_organization_person_id (str): LIF organization person ID.
            mapping_id (str): Mapping ID to delete.

        Raises:
            ValueError: If the input data is invalid.
            DataNotFoundException: If the mapping is not found.
            DataStoreException: If there is an error deleting the mapping.
        """
        if not lif_organization_id or not lif_organization_person_id or not mapping_id:
            raise ValueError("Invalid input data for deleting mapping")

        deleted_mapping: IdentityMapping | None = await self.storage.delete_mapping_by_id(mapping_id)
        if deleted_mapping is None:
            raise DataNotFoundException(f"Mapping not found for ID: {mapping_id}")
        if deleted_mapping.lif_organization_id != lif_organization_id:
            raise ValueError("LIF organization ID in mapping does not match the provided LIF organization ID")
        if deleted_mapping.lif_organization_person_id != lif_organization_person_id:
            raise ValueError(
                "LIF organization person ID in mapping does not match the provided LIF organization person ID"
            )
