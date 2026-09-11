import asyncio
from typing import List

from lif.datatypes import IdentityMapping
from lif.exceptions.core import DataStoreException
from lif.identity_mapper_storage.core import DeleteOutcome, IdentityMapperStorage
from lif.identity_mapper_storage_sql.model import IdentityMappingModel
from lif.identity_mapper_storage_sql.crud import create_all, read, read_by_lif_org_and_person, delete


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
        except ValueError:
            raise
        except Exception as e:
            raise DataStoreException from e

    async def save_mappings(self, identity_mappings: List[IdentityMapping]) -> List[IdentityMapping]:
        """
        Save a collection of identity mappings in a single transaction.

        Existing mappings are updated, new ones are created, and unchanged ones are
        returned as-is. The whole batch commits atomically: any failure rolls back
        every change. One entry is returned per persisted row, so a batch carrying the
        same key twice yields one entry, not two.
        Raises ValueError for a caller error (an unrecognized `mapping_id`, or one whose
        row does not match the target system fields sent with it).
        Raises DataStoreException for database-related errors.
        """
        try:
            return await asyncio.to_thread(self._save_mappings, identity_mappings)
        except ValueError:
            raise
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
                        existing_by_key[self._model_key(existing)] = existing
                        existing_by_mapping_id[existing.mapping_id] = existing

                new_models: List[IdentityMappingModel] = []
                saved_models: List[IdentityMappingModel] = []
                for mapping in identity_mappings:
                    key = (
                        mapping.lif_organization_id,
                        mapping.lif_organization_person_id,
                        mapping.target_system_id,
                        mapping.target_system_person_id_type,
                    )
                    existing: IdentityMappingModel | None = self._resolve_existing(
                        mapping, key, existing_by_key, existing_by_mapping_id
                    )
                    if existing is None:
                        mapping_model = IdentityMappingModel()
                        mapping_model.from_identity_mapping(mapping)
                        new_models.append(mapping_model)
                        existing_by_key[key] = mapping_model
                        existing_by_mapping_id[mapping_model.mapping_id] = mapping_model
                        saved_models.append(mapping_model)
                    else:
                        if existing.target_system_person_id != mapping.target_system_person_id:
                            existing.target_system_person_id = mapping.target_system_person_id
                        saved_models.append(existing)

                # One flush for the whole batch: `create_all` only stages the inserts and the
                # session already tracks the updates, so a 500-mapping batch flushes once
                # rather than once per row. The uuid is assigned in Python
                # (`from_identity_mapping`), which is what removes the need to flush each
                # insert just to materialize its primary key.
                if new_models:
                    create_all(session, new_models)
                session.flush()

                return [IdentityMapping.model_validate(model) for model in self._dedupe(saved_models)]

    @staticmethod
    def _model_key(model: IdentityMappingModel) -> tuple[str, str, str, str]:
        return (
            model.lif_organization_id,
            model.lif_organization_person_id,
            model.target_system_id,
            model.target_system_person_id_type,
        )

    def _resolve_existing(
        self,
        mapping: IdentityMapping,
        key: tuple[str, str, str, str],
        existing_by_key: dict[tuple[str, str, str, str], IdentityMappingModel],
        existing_by_mapping_id: dict[str, IdentityMappingModel],
    ) -> IdentityMappingModel | None:
        """
        Resolve the row a mapping refers to, or None when it is new.

        A supplied `mapping_id` must name a row this caller already owns. Falling through
        to the create branch instead would copy that id into a new row's primary key and
        raise an opaque IntegrityError, discarding the rest of the batch with it.
        """
        if mapping.mapping_id is None:
            return existing_by_key.get(key)

        existing = existing_by_mapping_id.get(mapping.mapping_id)
        if existing is None:
            raise ValueError(
                f"Unknown mapping_id '{mapping.mapping_id}' for this organization and person; "
                "omit it to create a new mapping"
            )
        if self._model_key(existing) != key:
            raise ValueError(
                f"mapping_id '{mapping.mapping_id}' identifies a mapping for target system "
                f"'{existing.target_system_id}' / '{existing.target_system_person_id_type}', "
                f"not '{mapping.target_system_id}' / '{mapping.target_system_person_id_type}'"
            )
        return existing

    @staticmethod
    def _dedupe(models: List[IdentityMappingModel]) -> List[IdentityMappingModel]:
        """One entry per persisted row, in first-seen order."""
        seen: set[str] = set()
        unique: List[IdentityMappingModel] = []
        for model in models:
            if model.mapping_id in seen:
                continue
            seen.add(model.mapping_id)
            unique.append(model)
        return unique

    async def delete_mapping_for_owner(
        self, mapping_id: str, lif_organization_id: str, lif_organization_person_id: str
    ) -> DeleteOutcome:
        """
        Delete the identity mapping identified by mapping_id, only if it belongs to the
        given LIF organization and person.
        Raises DataStoreException for database-related errors.
        """
        try:
            return await asyncio.to_thread(
                self._delete_mapping_for_owner, mapping_id, lif_organization_id, lif_organization_person_id
            )
        except Exception as e:
            raise DataStoreException from e

    def _delete_mapping_for_owner(
        self, mapping_id: str, lif_organization_id: str, lif_organization_person_id: str
    ) -> DeleteOutcome:
        # Read, authorize, and delete inside ONE transaction. `session.begin()` commits
        # when this block exits, so any ownership check placed after the block runs
        # against an already-durable delete and cannot undo it (#1150). Returning early
        # on a mismatch leaves the transaction with no pending delete to commit.
        with self.db_session_factory() as session:
            with session.begin():
                existing: IdentityMappingModel | None = read(session, mapping_id)
                if existing is None:
                    return DeleteOutcome.NOT_FOUND
                if (
                    existing.lif_organization_id != lif_organization_id
                    or existing.lif_organization_person_id != lif_organization_person_id
                ):
                    return DeleteOutcome.NOT_OWNED
                delete(session, existing)
                return DeleteOutcome.DELETED
