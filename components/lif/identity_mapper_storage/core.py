from enum import Enum
from typing import List, Protocol
from lif.datatypes import IdentityMapping


class DeleteOutcome(Enum):
    """Result of an ownership-scoped delete.

    Distinguishing NOT_FOUND from NOT_OWNED lets the service keep its 404-vs-400
    responses while the ownership check runs inside the delete's own transaction
    (#1150). A bare Optional cannot express that difference.
    """

    DELETED = "DELETED"
    NOT_FOUND = "NOT_FOUND"
    NOT_OWNED = "NOT_OWNED"


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

    async def delete_mapping_for_owner(
        self, mapping_id: str, lif_organization_id: str, lif_organization_person_id: str
    ) -> DeleteOutcome:
        """
        Delete the identity mapping identified by mapping_id, but only if it belongs to
        the given LIF organization and person.

        The ownership check MUST happen in the same transaction as the delete. Checking
        after the delete has committed lets one organization remove another's mapping
        (#1150), which no error raised afterwards can undo.

        Returns DELETED when the row was removed, NOT_FOUND when no row has that
        mapping_id, and NOT_OWNED when a row exists but belongs to someone else. In the
        NOT_OWNED case nothing is deleted.
        """
