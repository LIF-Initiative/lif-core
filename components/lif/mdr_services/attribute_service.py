from typing import List
from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import (
    Attribute,
    DataModelType,
    ElementType,
    EntityAttributeAssociation,
    ExtInclusionsFromBaseDM,
    Transformation,
    TransformationAttribute,
    TransformationGroup,
)
from lif.mdr_dto.attribute_dto import (
    AttributeDTO,
    AttributeWithAssociationMetadataDTO,
    CreateAttributeDTO,
    UpdateAttributeDTO,
)
from lif.mdr_services.helper_service import check_datamodel_by_id, check_entity_by_id
from lif.mdr_services.value_set_values_service import check_value_set_exists_by_id
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import or_, select, func


logger = get_logger(__name__)


async def get_paginated_attributes(session: AsyncSession, offset: int = 0, limit: int = 10, pagination: bool = True):
    # Step 1: Query to count total non-deleted records
    total_query = select(func.count(Attribute.Id)).where(Attribute.Deleted == False)
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    # Step 2: Query to fetch paginated results (non-deleted records only)
    if pagination:
        query = select(Attribute).where(Attribute.Deleted == False).offset(offset).limit(limit)
    else:
        query = select(Attribute).where(Attribute.Deleted == False)
    result = await session.execute(query)
    attributes = result.scalars().all()

    # association_dict = await get_entity_attribute_association_dict(session=session)

    attribute_dtos = []

    for attribute in attributes:
        attribute_dto = AttributeDTO.from_orm(attribute)
        # if attribute_dto.Id in association_dict:
        #     attribute_dto.EntityId = association_dict[attribute_dto.Id]
        attribute_dtos.append(attribute_dto)

    return total_count, attribute_dtos


async def get_attribute_dto_by_id(session: AsyncSession, id: int):
    attribute = await session.get(Attribute, id)
    if not attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    if attribute.Deleted:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} is deleted")
    # association_dict = await get_entity_attribute_association_dict(session=session)
    attribute_dto = AttributeDTO.from_orm(attribute)
    # if attribute_dto.Id in association_dict:
    #     attribute_dto.EntityId = association_dict[attribute_dto.Id]
    return attribute_dto


async def get_attribute_by_id(session: AsyncSession, id: int):
    attribute = await session.get(Attribute, id)
    if not attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    if attribute.Deleted:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} is deleted")
    return attribute


async def create_attribute(session: AsyncSession, data: CreateAttributeDTO):
    # Checking if data model and entity exists or not
    data_model = await check_datamodel_by_id(session=session, id=data.DataModelId)

    if data_model.BaseDataModelId and not data.Extension:
        data.Extension = True
    if not data_model.BaseDataModelId and data.Extension:
        logger.info("Data model is not extension so provided attribute can not be an extension.")
        data.Extension = False

    existing_attribute = await check_attribute_exists(session, data.UniqueName, data.DataModelId)
    if existing_attribute:
        raise HTTPException(
            status_code=400,
            detail=f"Attribute with unique name {data.UniqueName} already exists for DataModel {data.DataModelId}.",
        )

    # If creating with value set, check if value set exists
    if data.ValueSetId:
        await check_value_set_exists_by_id(session=session, id=data.ValueSetId)

    # When an EntityId is supplied, create the attribute AND its entity association in a single
    # transaction. Previously the UI created these via two separate, independently-committed
    # requests; if the first response was lost the client never issued the second, leaving the
    # attribute persisted but unassociated — invisible in the entity view yet blocking re-create
    # on the unique name (#1028). One commit means a dropped response leaves either nothing or a
    # fully-associated (visible) attribute, never an orphan.
    if data.EntityId is not None:
        await check_entity_by_id(session=session, id=data.EntityId)

    attribute = Attribute(**data.dict(exclude={"EntityId"}))
    session.add(attribute)

    try:
        if data.EntityId is not None:
            await session.flush()  # assign attribute.Id without committing
            # For an extension model (OrgLIF/PartnerLIF — data.Extension is derived from the model's
            # BaseDataModelId above), the association is an extension placement onto this model, matching
            # the frontend's tmplCreateEntityAttributeAssociation (ExtendedByDataModelId = the model id).
            association = EntityAttributeAssociation(
                EntityId=data.EntityId,
                AttributeId=attribute.Id,
                Contributor=data.Contributor,
                ContributorOrganization=data.ContributorOrganization,
                Deleted=False,
                ExtendedByDataModelId=data.DataModelId if data.Extension else None,
            )
            session.add(association)
        await session.commit()
    except Exception:
        # Keep the create atomic: if the association or commit fails, roll back the attribute too,
        # so we never persist a half-created (orphaned) attribute (#1028).
        await session.rollback()
        raise

    await session.refresh(attribute)
    attribute_dto = AttributeDTO.from_orm(attribute)
    return attribute_dto


async def check_attribute_exists(session, unique_name, data_model_id):
    query = select(Attribute).where(
        Attribute.UniqueName == unique_name, Attribute.DataModelId == data_model_id, Attribute.Deleted == False
    )
    result = await session.execute(query)
    return result.scalars().first()


async def update_attribute(session: AsyncSession, id: int, data: UpdateAttributeDTO):
    attribute = await session.get(Attribute, id)
    if not attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    if attribute.Deleted:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} is deleted")

    # Checking if data model exists or not
    if data.DataModelId:
        await check_datamodel_by_id(session=session, id=data.DataModelId)

    # Checking if attribute with same unique name exists
    if data.UniqueName or data.DataModelId:
        updated_unique_name = data.UniqueName if data.UniqueName else attribute.UniqueName
        updated_data_model_id = data.DataModelId if data.DataModelId else attribute.DataModelId
        existing_attribute = await check_attribute_exists(session, updated_unique_name, updated_data_model_id)
        logger.info(f"Existing attribute: {existing_attribute}")
        if existing_attribute and existing_attribute.Id != id:
            raise HTTPException(
                status_code=400,
                detail=f"Attribute with UniqueName {updated_unique_name} already exists for DataModel {updated_data_model_id}.",
            )

    # If updating with value set, check if value set exists
    if data.ValueSetId:
        await check_value_set_exists_by_id(session=session, id=data.ValueSetId)

    for key, value in data.dict(exclude_unset=True).items():
        setattr(attribute, key, value)

    session.add(attribute)
    await session.commit()
    await session.refresh(attribute)

    attribute_dto = AttributeDTO.from_orm(attribute)
    return attribute_dto


async def delete_attribute(session: AsyncSession, id: int):
    # Fetch the attribute by ID
    attribute = await session.get(Attribute, id)
    if not attribute:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} not found")
    if attribute.Deleted:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} is already deleted")

    try:
        # Delete associations in the EntityAttributeAssociation table
        association_query = select(EntityAttributeAssociation).where(EntityAttributeAssociation.AttributeId == id)
        result = await session.execute(association_query)
        associations = result.scalars().all()

        # Delete all associated records from EntityAttributeAssociation
        for association in associations:
            await session.delete(association)

        # Now delete the attribute itself
        await session.delete(attribute)
        await session.commit()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting attribute and associations: {str(e)}")

    return {"ok": True}


async def soft_delete_attribute(session: AsyncSession, id: int):
    # Fetch the attribute by ID
    attribute = await session.get(Attribute, id)
    if not attribute:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} not found")
    if attribute.Deleted:
        raise HTTPException(status_code=404, detail=f"Attribute with ID {id} is already deleted")

    try:
        # Delete associations in the EntityAttributeAssociation table
        association_query = select(EntityAttributeAssociation).where(
            EntityAttributeAssociation.AttributeId == id, EntityAttributeAssociation.Deleted == False
        )
        result = await session.execute(association_query)
        associations = result.scalars().all()
        for association in associations:
            association.Deleted = True
            session.add(association)

        # Delete attribute inclusions in the ExtInclusionsFromBaseDM table
        ext_inclusion_query = select(ExtInclusionsFromBaseDM).where(
            ExtInclusionsFromBaseDM.ElementType == ElementType.Attribute,
            ExtInclusionsFromBaseDM.IncludedElementId == id,
            ExtInclusionsFromBaseDM.Deleted == False,
        )
        result = await session.execute(ext_inclusion_query)
        ext_inclusions = result.scalars().all()
        for ext_inclusion in ext_inclusions:
            ext_inclusion.Deleted = True
            session.add(ext_inclusion)

        # Delete Transformation and Transformation attributes
        transformation_attribute_query = (
            select(TransformationAttribute.TransformationId)
            .distinct()
            .where(TransformationAttribute.AttributeId == id, TransformationAttribute.Deleted == False)
        )
        result = await session.execute(transformation_attribute_query)
        transformation_ids = result.scalars().all()
        transformation_group_ids = []
        for transformation_id in transformation_ids:
            transformation_query = select(Transformation).where(
                Transformation.Id == transformation_id, Transformation.Deleted == False
            )
            result = await session.execute(transformation_query)
            transformation = result.scalars().first()
            transformation.Deleted = True
            transformation_group_ids.append(transformation.TransformationGroupId)

            transformation_attribute_query = select(TransformationAttribute).where(
                TransformationAttribute.TransformationId == transformation_id, TransformationAttribute.Deleted == False
            )
            result = await session.execute(transformation_attribute_query)
            transformation_attributes = result.scalars().all()
            for transformation_attribute in transformation_attributes:
                transformation_attribute.Deleted = True
                session.add(transformation_attribute)
        for group_id in set(transformation_group_ids):
            transformation_query = select(Transformation).where(
                Transformation.Id.notin_(transformation_ids),
                Transformation.TransformationGroupId == group_id,
                Transformation.Deleted == False,
            )
            result = await session.execute(transformation_query)
            transformation = result.scalars().all()
            if not transformation:
                transformation_group_query = select(TransformationGroup).where(
                    TransformationGroup.Id == group_id, Transformation.Deleted == False
                )
                result = await session.execute(transformation_group_query)
                transformation_group = result.scalars().first()
                transformation_group.Deleted = True
                session.add(transformation_group)

        # Now delete the attribute itself
        attribute.Deleted = True
        session.add(attribute)

        await session.commit()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting attribute and associations: {str(e)}")

    return {"ok": True}


async def get_attributes_by_ids(session: AsyncSession, id_list: List[int]):
    # Query to get the attributes for the provided list of IDs
    query = select(Attribute).where(Attribute.Id.in_(id_list), Attribute.Deleted == False).order_by(Attribute.Id)
    result = await session.execute(query)
    attributes = result.scalars().all()

    # Convert the list of Attribute objects to AttributeDTO objects
    attribute_dtos = []

    for attribute in attributes:
        attribute_dto = AttributeDTO.from_orm(attribute)
        attribute_dtos.append(attribute_dto)

    return attribute_dtos


async def get_list_of_attributes_for_entity(
    session: AsyncSession,
    entity_id: int,
    data_model_id: int,
    data_model_type: str = None,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    this_organization: str = "LIF",
    partner_only: bool = False,
    org_ext_only: bool = False,
    public_only: bool = False,
):
    # Step 1: Get the AttributeIds from the EntityAttributeAssociation table
    if data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        attribute_ids_query = select(EntityAttributeAssociation.AttributeId).where(
            EntityAttributeAssociation.EntityId == entity_id,
            EntityAttributeAssociation.Deleted == False,
            or_(
                EntityAttributeAssociation.ExtendedByDataModelId == data_model_id,
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
            ),
        )
    else:
        attribute_ids_query = select(EntityAttributeAssociation.AttributeId).where(
            EntityAttributeAssociation.EntityId == entity_id,
            EntityAttributeAssociation.Deleted == False,
            EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
        )
    attribute_ids_result = await session.execute(attribute_ids_query)
    attribute_ids = attribute_ids_result.scalars().all()
    logger.info(f"Attribute IDs for Entity {entity_id}: {attribute_ids}")

    if not attribute_ids:
        return 0, []  # No attributes found for the given entity

    # Step 2: If OrgLIF or PartnerLIF, filter to only entities included for this org's data model
    if data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        # Query to fetch IncludedElementId from ExtInclusionsFromBaseDM table where ElementType = Attribute and IncludedElementId in attribute_ids
        ext_inclusions_query = select(ExtInclusionsFromBaseDM.IncludedElementId).where(
            ExtInclusionsFromBaseDM.ElementType == "Attribute",
            ExtInclusionsFromBaseDM.IncludedElementId.in_(attribute_ids),
            ExtInclusionsFromBaseDM.Deleted == False,
        )
        if org_ext_only:
            ext_inclusions_query = ext_inclusions_query.where(
                (ExtInclusionsFromBaseDM.ContributorOrganization == this_organization)
            )
        if partner_only:
            ext_inclusions_query = ext_inclusions_query.where(
                (ExtInclusionsFromBaseDM.ContributorOrganization != "LIF")
                & (ExtInclusionsFromBaseDM.ContributorOrganization != this_organization)
            )
        if public_only:
            ext_inclusions_query = ext_inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")

        # Step 2: Count total attributes for pagination
        total_result = await session.execute(ext_inclusions_query)
        attribute_ids = total_result.scalars().all()
        total_count = len(attribute_ids)
    else:
        # Step 2: Count total attributes for pagination
        total_query = select(func.count(Attribute.Id)).where(
            Attribute.Id.in_(attribute_ids), Attribute.Deleted == False
        )
        total_result = await session.execute(total_query)
        total_count = total_result.scalar()

    # Step 3: Fetch paginated attributes using the AttributeIds, ordered by Id
    if pagination:
        query = (
            select(Attribute)
            .where(Attribute.Id.in_(attribute_ids), Attribute.Deleted == False)
            .order_by(Attribute.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        query = (
            select(Attribute).where(Attribute.Id.in_(attribute_ids), Attribute.Deleted == False).order_by(Attribute.Id)
        )
    result = await session.execute(query)
    attributes = result.scalars().all()

    # Convert to AttributeDTO list
    attribute_dtos = []
    for attribute in attributes:
        # Create a new AttributeDTO and add the EntityId
        attribute_dto = AttributeDTO.from_orm(attribute)
        attribute_dtos.append(attribute_dto)

    return total_count, attribute_dtos


async def get_attributes_with_association_metadata_for_entity(
    session: AsyncSession, entity_id: int, data_model_id: int, data_model_type: str = None, public_only: bool = False
):
    # Step 1: Get EntityAttributeAssociation records for the entity
    if data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        association_query = select(EntityAttributeAssociation).where(
            EntityAttributeAssociation.EntityId == entity_id,
            EntityAttributeAssociation.Deleted == False,
            or_(
                EntityAttributeAssociation.ExtendedByDataModelId == data_model_id,
                EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
            ),
        )
    else:
        association_query = select(EntityAttributeAssociation).where(
            EntityAttributeAssociation.EntityId == entity_id,
            EntityAttributeAssociation.Deleted == False,
            EntityAttributeAssociation.ExtendedByDataModelId.is_(None),
        )
    association_result = await session.execute(association_query)
    associations = association_result.scalars().all()
    logger.info(f"Associations for Entity {entity_id}: {associations}")

    if not associations:
        return []  # No attributes found for the given entity

    attribute_ids = [assoc.AttributeId for assoc in associations]
    attribute_map = {assoc.AttributeId: assoc for assoc in associations}
    # Step 2: If OrgLIF or PartnerLIF, filter to only entities included for this org's data model
    if data_model_type == DataModelType.OrgLIF or data_model_type == DataModelType.PartnerLIF:
        # Query to fetch IncludedElementId from ExtInclusionsFromBaseDM table where ElementType = Attribute and IncludedElementId in attribute_ids
        ext_inclusions_query = select(ExtInclusionsFromBaseDM.IncludedElementId).where(
            ExtInclusionsFromBaseDM.ElementType == "Attribute",
            ExtInclusionsFromBaseDM.IncludedElementId.in_(attribute_ids),
            ExtInclusionsFromBaseDM.Deleted == False,
        )
        if public_only:
            ext_inclusions_query = ext_inclusions_query.where(ExtInclusionsFromBaseDM.LevelOfAccess == "Public")

        # Step 2: Count total attributes for pagination
        total_result = await session.execute(ext_inclusions_query)
        attribute_ids = total_result.scalars().all()
    # Step 3: Fetch attributes using the AttributeIds, ordered by Id
    query = select(Attribute).where(Attribute.Id.in_(attribute_ids), Attribute.Deleted == False).order_by(Attribute.Id)
    result = await session.execute(query)
    attributes = result.scalars().all()
    # Convert to AttributeWithAssociationMetadataDTO list
    attribute_dtos = []
    for attribute in attributes:
        # Create a new AttributeDTO and add the EntityId
        attribute_dto = AttributeWithAssociationMetadataDTO.from_orm(attribute)
        if attribute.Id in attribute_map:
            assoc = attribute_map[attribute.Id]
            attribute_dto.EntityAttributeAssociationId = assoc.Id
            attribute_dto.EntityId = assoc.EntityId
            attribute_dto.AssociationNotes = assoc.Notes
            attribute_dto.AssociationCreationDate = assoc.CreationDate
            attribute_dto.AssociationActivationDate = assoc.ActivationDate
            attribute_dto.AssociationDeprecationDate = assoc.DeprecationDate
            attribute_dto.AssociationContributor = assoc.Contributor
            attribute_dto.AssociationContributorOrganization = assoc.ContributorOrganization
            attribute_dto.AssociationExtendedByDataModelId = assoc.ExtendedByDataModelId
        attribute_dtos.append(attribute_dto)
    return attribute_dtos


async def get_list_of_attributes_for_data_model(
    session: AsyncSession,
    data_model_id: int,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    check_base: bool = True,
):
    data_model_id_list: List[int] = []
    data_model = await check_datamodel_by_id(session=session, id=data_model_id)
    data_model_id_list.append(data_model.Id)
    if check_base and (data_model.Type == DataModelType.OrgLIF or data_model.Type == DataModelType.PartnerLIF):
        base_data_model = await check_datamodel_by_id(session=session, id=data_model.BaseDataModelId)
        data_model_id_list.append(base_data_model.Id)

    # Step 1: Count total attributes for pagination
    total_query = select(func.count(Attribute.Id)).where(
        Attribute.DataModelId.in_(data_model_id_list), Attribute.Deleted == False
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    # Step 2: Fetch paginated attributes using the AttributeIds, ordered by Id
    if pagination:
        query = (
            select(Attribute)
            .where(Attribute.DataModelId.in_(data_model_id_list), Attribute.Deleted == False)
            .order_by(Attribute.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        query = (
            select(Attribute)
            .where(Attribute.DataModelId.in_(data_model_id_list), Attribute.Deleted == False)
            .order_by(Attribute.Id)
        )
    result = await session.execute(query)
    attributes = result.scalars().all()
    attribute_dtos = []

    for attribute in attributes:
        attribute_dto = AttributeDTO.from_orm(attribute)
        attribute_dtos.append(attribute_dto)

    return total_count, attribute_dtos
