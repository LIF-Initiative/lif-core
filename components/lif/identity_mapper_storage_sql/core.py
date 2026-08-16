import asyncio
from typing import List

from lif.datatypes import IdentityMapping
from lif.exceptions.core import DataStoreException
from lif.identity_mapper_storage.core import IdentityMapperStorage
from lif.identity_mapper_storage_sql.model import IdentityMappingModel
from lif.identity_mapper_storage_sql.crud import create, read, read_by_lif_org_and_person, delete


class IdentityMapperSqlStorage(IdentityMapperStorage):
    """
    An implementation of IdentityMapperStorage that uses an SQL database for data storage.
    """

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    async def get_mapping_by_id(self, mapping_id: str) -> IdentityMapping | None:
        """
        Retrieve an identity mapping by its ID.
        Returns None if the mapping does not exist.
        Raises DataStoreException for database-related errors.
        """
        try:
            return await asyncio.to_thread(self._get_mapping_by_id, mapping_id)
        except Exception as e:
            raise DataStoreException from e

    def _get_mapping_by_id(self, mapping_id: str) -> IdentityMapping | None:
        with self.db_session_factory() as session:
            with session.begin():
                mapping_model: IdentityMappingModel | None = read(session, mapping_id)
                if mapping_model:
                    return IdentityMapping.model_validate(mapping_model)
                else:
                    return None

    async def get_mappings(self, lif_organization_id: str, lif_organization_person_id: str) -> List[IdentityMapping]:
        """
        Retrieve identity mappings for a person in a LIF organization.
        Raises DataStoreException for database-related errors.
        """
        try:
            return await asyncio.to_thread(self._get_mappings, lif_organization_id, lif_organization_person_id)
        except Exception as e:
            raise DataStoreException from e

    def _get_mappings(self, lif_organization_id: str, lif_organization_person_id: str) -> List[IdentityMapping]:
        with self.db_session_factory() as session:
            with session.begin():
                mapping_models: List[IdentityMappingModel] = read_by_lif_org_and_person(
                    session, lif_organization_id, lif_organization_person_id
                )
                return [IdentityMapping.model_validate(mapping_model) for mapping_model in mapping_models]

    async def save_mapping(self, identity_mapping: IdentityMapping) -> IdentityMapping:
        """
        Save a single identity mapping.
        Raises DataStoreException for database-related errors.
        """
        try:
            saved: List[IdentityMapping] = await asyncio.to_thread(self._save_mappings, [identity_mapping])
            return saved[0]
        except Exception as e:
            raise DataStoreException from e

    async def save_mappings(self, identity_mappings: List[IdentityMapping]) -> List[IdentityMapping]:
        """
        Save a collection of identity mappings in a single transaction.

        Existing mappings are updated, new ones are created, and unchanged ones are
        returned as-is. The whole batch commits atomically: any failure rolls back
        every change.
        Raises DataStoreException for database-related errors.
        """
        try:
            return await asyncio.to_thread(self._save_mappings, identity_mappings)
        except Exception as e:
            raise DataStoreException from e

    def _save_mappings(self, identity_mappings: List[IdentityMapping]) -> List[IdentityMapping]:
        existing_by_key: dict[tuple[str, str, str, str], IdentityMappingModel] = {}
        existing_by_mapping_id: dict[str, IdentityMappingModel] = {}
        with self.db_session_factory() as session:
            with session.begin():
                seen_pairs: set[tuple[str, str]] = set()
                for mapping in identity_mappings:
                    pair = (mapping.lif_organization_id, mapping.lif_organization_person_id)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    for existing in read_by_lif_org_and_person(session, pair[0], pair[1]):
                        key = (
                            existing.lif_organization_id,
                            existing.lif_organization_person_id,
                            existing.target_system_id,
                            existing.target_system_person_id_type,
                        )
                        existing_by_key[key] = existing
                        existing_by_mapping_id[existing.mapping_id] = existing

                saved_models: List[IdentityMappingModel] = []
                for mapping in identity_mappings:
                    key = (
                        mapping.lif_organization_id,
                        mapping.lif_organization_person_id,
                        mapping.target_system_id,
                        mapping.target_system_person_id_type,
                    )
                    existing: IdentityMappingModel | None = (
                        existing_by_mapping_id.get(mapping.mapping_id)
                        if mapping.mapping_id is not None
                        else existing_by_key.get(key)
                    )
                    if existing is None:
                        mapping_model = IdentityMappingModel()
                        mapping_model.from_identity_mapping(mapping)
                        create(session, mapping_model)
                        existing_by_key[key] = mapping_model
                        existing_by_mapping_id[mapping_model.mapping_id] = mapping_model
                        saved_models.append(mapping_model)
                    elif existing.target_system_person_id != mapping.target_system_person_id:
                        existing.target_system_person_id = mapping.target_system_person_id
                        session.flush()
                        saved_models.append(existing)
                    else:
                        saved_models.append(existing)
                return [IdentityMapping.model_validate(model) for model in saved_models]

    async def delete_mapping_by_id(self, mapping_id: str) -> IdentityMapping | None:
        """
        Delete the identity mapping identified by the mapping_id.
        Returns the deleted IdentityMapping, or None if it did not exist.
        Raises DataStoreException for database-related errors.
        """
        try:
            return await asyncio.to_thread(self._delete_mapping_by_id, mapping_id)
        except Exception as e:
            raise DataStoreException from e

    def _delete_mapping_by_id(self, mapping_id: str) -> IdentityMapping | None:
        with self.db_session_factory() as session:
            with session.begin():
                existing: IdentityMappingModel | None = read(session, mapping_id)
                if existing is None:
                    return None
                delete(session, existing)
                return IdentityMapping.model_validate(existing)
