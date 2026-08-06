from typing import Dict, List

from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import (
    AttributeType,
    DataModel,
    DatamodelElementType,
    DataModelType,
    EntityAttributeAssociation,
    ExpressionLanguageType,
    Transformation,
    TransformationAttribute,
    TransformationGroup,
)
from lif.mdr_dto.transformation_dto import (
    CreateTransformationAttributeDTO,
    CreateTransformationDTO,
    CreateTransformationWithTransformationGroupDTO,
    GetALLTransformationsDTO,
    TransformationAttributeDTO,
    TransformationDTO,
    TransformationListDTO,
    UpdateTransformationDTO,
)
from lif.mdr_dto.transformation_group_dto import (
    CreateTransformationGroupDTO,
    DataModelRefDTO,
    ImportTransformationAttributeDTO,
    ImportTransformationGroupRequestDTO,
    ImportTransformationGroupResultDTO,
    TransformationGroupDTO,
    TransformationImportNonMatchDTO,
    UpdateTransformationGroupDTO,
)
from lif.mdr_services.attribute_service import get_attribute_dto_by_id, get_unique_attribute
from lif.mdr_services.entity_association_service import retrieve_all_entity_associations
from lif.mdr_services.entity_attribute_association_service import retrieve_all_entity_attribute_associations
from lif.mdr_services.entity_service import get_unique_entity
from lif.mdr_services.helper_service import check_attribute_by_id, check_datamodel_by_id, check_entity_by_id
from lif.mdr_services.inclusions_service import check_existing_inclusion
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import func, select

logger = get_logger(__name__)


def parse_transformation_path(id_path: str) -> List[int]:
    """
    Parses IDs from a transformation path string into a list of IDs which represent entity IDs (positive value) or attribute IDs (negative value).

    All IDs in the path are expected to be integers.

    :param id_path:
        Format is `id1,id2,...,idN`
    :type id_path: str
    :return: A list of entity (or attribute) IDs.
    """
    if not id_path:
        msg = "Invalid EntityIdPath format. The path must not be empty."
        logger.error(msg)
        raise HTTPException(status_code=400, detail=msg)

    ids = []
    for id_str in id_path.split(","):
        try:
            id = int(id_str)
            ids.append(id)
        except ValueError:
            logger.error(
                f"Invalid EntityIdPath format: '{id_path}'. IDs must be in the format 'id1,id2,...,idN' and all IDs must be integers."
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid EntityIdPath format. IDs must be in the format 'id1,id2,...,idN' and all IDs must be integers.",
            )

    if len(ids) < 1:
        logger.error(f"Invalid EntityIdPath format: '{id_path}'. The path must contain at least one ID.")
        raise HTTPException(
            status_code=400, detail="Invalid EntityIdPath format. The path must contain at least one ID."
        )

    return ids


async def check_transformation_attribute(session: AsyncSession, anchor_data_model: DataModel, id_path: str):
    """
    Confirms the provided ID path is valid for the given transformation attribute.

    :param session: DB session
    :param anchor_data_model: Data model for the anchor of this transformation attribute. Should be either the source or target data model for the transformation group.
    :param id_path: ID path representing the chain of entity IDs with the final ID possibly being an attribute ID (which is marked as such by a negative sign).

    - The path must be in the correct format and contain at least one ID.
    - The path may end with a non-deleted attribute, and the rest be non-deleted entities.
    - If the anchor data model is a Base LIF or Source Schema, all entities and attributes in the path must originate from the anchor data model.
    - For Org LIF and Partner LIF anchor data models, the entities and attributes must be included in the anchor data model.
    - Entities and attributes via (Entity/Attribute.DataModelId) must belong to the anchor data model or be included in (ExtInclusionFromBaseDM.ExtDataModelId).
    - Entities and attributes must 'chain' together via the association tables. This is different based on the type of the anchor data model.
    """
    transformation_path_ids = parse_transformation_path(id_path)
    previous_node = None
    current_node = None
    for i, raw_node_id in enumerate(transformation_path_ids):
        # Gather details

        is_last_node = i == len(transformation_path_ids) - 1
        # if it's the last node and negative it's an attribute, otherwise it's an entity
        node_type = DatamodelElementType.Attribute if is_last_node and raw_node_id < 0 else DatamodelElementType.Entity
        cleaned_node_id = abs(raw_node_id)
        initial_signature = f"Node {raw_node_id}({cleaned_node_id}) in the entityIdPath ({id_path})"
        # Also confirms the entity / attribute exists and is not deleted
        try:
            # If there is a current node, capture it as the previous node for association checks.
            if current_node:
                previous_node = current_node
            current_node = (
                await check_entity_by_id(session=session, id=cleaned_node_id)
                if node_type == DatamodelElementType.Entity
                else await check_attribute_by_id(session=session, id=cleaned_node_id)
            )
            node_data_model_id = current_node.DataModelId
        except HTTPException as e:
            logger.error(f"{initial_signature} - {e.detail}")
            raise
        initial_signature = f"Node {raw_node_id}({cleaned_node_id}) with originating data model ({node_data_model_id}) in the entityIdPath ({id_path})"

        anchor_data_model_id = anchor_data_model.Id
        is_self_contained_anchor_model = anchor_data_model.Type in [DataModelType.BaseLIF, DataModelType.SourceSchema]
        originates_in_anchor = anchor_data_model_id == node_data_model_id
        if node_type == DatamodelElementType.Entity and raw_node_id < 0:
            message = f"{initial_signature} - Invalid EntityIdPath format. Only the last ID in the path can be an attribute ID (negative value)."
            logger.error(message)
            raise HTTPException(status_code=400, detail=message)
        signature = f"{node_type.name} {raw_node_id}({cleaned_node_id}) with originating data model ({node_data_model_id}) in the entityIdPath ({id_path})"
        logger.info(f"{signature} - Checking node against the anchor data model {anchor_data_model_id}")

        # Validations

        if is_self_contained_anchor_model:
            if not originates_in_anchor:
                message = f"{signature} - Does not originate in the anchor data model {anchor_data_model_id}, which is a self-contained data model"
                logger.warning(message)
                raise HTTPException(status_code=400, detail=message)
            logger.info(f"{signature} - Originates in the self-contained anchor data model {anchor_data_model_id}.")

        if not is_self_contained_anchor_model:
            # Will only be checked for Org LIF and Partner LIF anchor data models, but should _always_ be checked for those data model types.
            await check_existing_inclusion(
                session=session, type=node_type, node_id=cleaned_node_id, included_by_data_model_id=anchor_data_model_id
            )
            logger.info(
                f"{signature} - Is included in the non-self-contained anchor data model {anchor_data_model_id}."
            )

        # First node has no association checks needed, check the rest for associations (ie all that have a previous node to associate from)
        if previous_node:
            associations = (
                await retrieve_all_entity_associations(
                    session=session,
                    parent_entity_id=previous_node.Id,
                    child_entity_id=raw_node_id,
                    extended_by_data_model_id=anchor_data_model_id,
                )
                if node_type == DatamodelElementType.Entity
                else await retrieve_all_entity_attribute_associations(
                    session=session,
                    entity_id=previous_node.Id,
                    attribute_id=abs(raw_node_id),
                    extended_by_data_model_id=anchor_data_model_id,
                )
            )
            logger.info(f"{signature} - Retrieved {len(associations)} associations to review.")

            found_valid_association = False
            # An association is either for an entity or attribute
            for association in associations:
                logger.info(f"{signature} - Reviewing association {association.Id}: {association}")
                if is_self_contained_anchor_model:
                    if (node_type == DatamodelElementType.Entity and association.Extension == True) or (
                        association.ExtendedByDataModelId is not None
                    ):
                        # Base LIF and Source Schema should not have extensions
                        message = f"{signature} - Association from parent {previous_node.Id} to child {raw_node_id} is marked as an extension, but {anchor_data_model.Id} is a self-contained data model."
                        logger.warning(f"{message} - association: {association}")
                        raise HTTPException(status_code=400, detail=message)
                    found_valid_association = True
                    logger.info(
                        f"{signature} - Association from parent {previous_node.Id} to child {raw_node_id} in the self-contained model is valid"
                    )
                    break
                else:
                    # Org LIF and Partner LIF may have extensions
                    if node_type == DatamodelElementType.Entity:
                        # If either the current or previous node is an Extension, the association must
                        # be an extension and have ExtendedByDataModelId set to the anchor data model
                        if (
                            (current_node.Extension == True or previous_node.Extension == True)
                            and association.Extension == True
                            and association.ExtendedByDataModelId == anchor_data_model_id
                        ):
                            found_valid_association = True
                            logger.info(
                                f"{signature} - Entity association from parent {previous_node.Id} to child {raw_node_id} is valid (Extension on current or parent is True, and association is an extension with extendedByDataModelId matching the anchor data model)"
                            )
                            break
                        # If both the current and previous nodes are not Extensions, the association must not
                        # be an extension but must have ExtendedByDataModelId set to the anchor data model
                        elif (
                            current_node.Extension == False
                            and previous_node.Extension == False
                            and association.Extension == False
                            and (
                                # A value of 'None' looks to occur when a mapping is requested of A1
                                # and the path is E1 > E2 > A1, but E1 was the association from
                                # the originating data model
                                association.ExtendedByDataModelId is anchor_data_model_id
                                or association.ExtendedByDataModelId is None
                            )
                        ):
                            found_valid_association = True
                            logger.info(
                                f"{signature} - Entity association from parent {previous_node.Id} to child {raw_node_id} is valid (Extension on current, parent, and association is false, but the association ExtendedByDataModelId matches the anchor data model)"
                            )
                            break
                        logger.info(
                            f"{signature} - Invalid non-self-contained data model entity association from parent (id={previous_node.Id}, extension={previous_node.Extension}) to child (id={raw_node_id}, extension={current_node.Extension}) is invalid: {association}"
                        )
                    else:
                        # Must be an attribute association

                        # If either the current or previous node is an Extension, the association
                        # must have ExtendedByDataModelId set to the anchor data model
                        if (
                            current_node.Extension == True or previous_node.Extension == True
                        ) and association.ExtendedByDataModelId == anchor_data_model_id:
                            found_valid_association = True
                            logger.info(
                                f"{signature} - Attribute association from parent {previous_node.Id} to child {raw_node_id} is valid (Extension on current or parent is True, and association's extendedByDataModelId matches the anchor data model)"
                            )
                            break
                        # If both the current and previous nodes are not Extensions, the
                        # association must have ExtendedByDataModelId set to the None
                        elif (
                            current_node.Extension == False
                            and previous_node.Extension == False
                            and (
                                association.ExtendedByDataModelId is None
                                or association.ExtendedByDataModelId == anchor_data_model_id
                            )
                        ):
                            found_valid_association = True
                            logger.info(
                                f"{signature} - Attribute association from parent {previous_node.Id} to child {raw_node_id} is valid (Extension on current and parent are false, and the association ExtendedByDataModelId is None or the anchor data model)"
                            )
                            break
                        logger.info(
                            f"{signature} - Invalid non-self-contained data model attribute association from parent (id={previous_node.Id}, extension={previous_node.Extension}) to child (id={raw_node_id}, extension={current_node.Extension}) is invalid: {association}"
                        )

            if not found_valid_association:
                message = f"{signature} - Unable to find valid association from parent {previous_node.Id} to child {raw_node_id}."
                logger.warning(f"{message} ")
                raise HTTPException(status_code=400, detail=message)

        # this will always be a positive id except for possibly the last node
        previous_id = raw_node_id


async def create_transformation(session: AsyncSession, data: CreateTransformationDTO, commit: bool = True):
    # When commit=False the caller owns the transaction boundary (used by the group import so the
    # whole import is one atomic transaction); we flush to obtain generated IDs but never commit.
    # Checking if transformation group exists
    transformation_group = await get_transformation_group_by_id(session=session, id=data.TransformationGroupId)
    source_data_model = await check_datamodel_by_id(session=session, id=transformation_group.SourceDataModelId)
    target_data_model = await check_datamodel_by_id(session=session, id=transformation_group.TargetDataModelId)

    # Validate source attributes
    for attribute in data.SourceAttributes:
        await check_transformation_attribute(
            session=session, anchor_data_model=source_data_model, id_path=attribute.EntityIdPath
        )

    # Validate target attributes
    await check_transformation_attribute(
        session=session, anchor_data_model=target_data_model, id_path=data.TargetAttribute.EntityIdPath
    )

    # Step 1: Create the Transformation
    transformation = Transformation(
        TransformationGroupId=data.TransformationGroupId,
        Name=data.Name,
        Expression=data.Expression,
        ExpressionLanguage=data.ExpressionLanguage,
        Notes=data.Notes,
        Alignment=data.Alignment,
        CreationDate=data.CreationDate,
        ActivationDate=data.ActivationDate,
        DeprecationDate=data.DeprecationDate,
        Contributor=data.Contributor,
        ContributorOrganization=data.ContributorOrganization,
    )
    session.add(transformation)
    # Flush (not commit) so the generated transformation.Id is available for the attributes below
    # without ending the transaction; the commit/flush decision is made once at the end.
    await session.flush()
    await session.refresh(transformation)

    # Step 2: Create TransformationAttributes (Source and Target)
    source_attributes = []
    for attribute in data.SourceAttributes:
        source_attribute = TransformationAttribute(
            TransformationId=transformation.Id,
            AttributeId=attribute.AttributeId,
            EntityId=attribute.EntityId,
            AttributeType="Source",
            Notes=attribute.Notes,
            CreationDate=attribute.CreationDate,
            ActivationDate=attribute.ActivationDate,
            DeprecationDate=attribute.DeprecationDate,
            Contributor=attribute.Contributor,
            ContributorOrganization=attribute.ContributorOrganization,
            EntityIdPath=attribute.EntityIdPath,
        )
        source_attributes.append(TransformationAttributeDTO.from_orm(source_attribute))
        session.add(source_attribute)

    target_attribute = TransformationAttribute(
        TransformationId=transformation.Id,
        AttributeId=data.TargetAttribute.AttributeId,
        EntityId=data.TargetAttribute.EntityId,
        AttributeType="Target",
        Notes=data.TargetAttribute.Notes,
        CreationDate=data.TargetAttribute.CreationDate,
        ActivationDate=data.TargetAttribute.ActivationDate,
        DeprecationDate=data.TargetAttribute.DeprecationDate,
        Contributor=data.TargetAttribute.Contributor,
        ContributorOrganization=data.TargetAttribute.ContributorOrganization,
        EntityIdPath=data.TargetAttribute.EntityIdPath,
    )

    session.add(target_attribute)
    if commit:
        await session.commit()
    else:
        await session.flush()

    # Step 3: Return the newly created TransformationDTO
    return TransformationDTO(
        Id=transformation.Id,
        TransformationGroupId=transformation.TransformationGroupId,
        Name=transformation.Name,
        ExpressionLanguage=transformation.ExpressionLanguage,
        Expression=transformation.Expression,
        Notes=transformation.Notes,
        Alignment=transformation.Alignment,
        CreationDate=transformation.CreationDate,
        ActivationDate=transformation.ActivationDate,
        DeprecationDate=transformation.DeprecationDate,
        Contributor=transformation.Contributor,
        ContributorOrganization=transformation.ContributorOrganization,
        SourceAttributes=source_attributes,
        TargetAttribute=TransformationAttributeDTO.from_orm(target_attribute),
    )


async def get_transformation_by_id(session: AsyncSession, transformation_id: int) -> dict:
    # Get the transformation
    transformation = await session.get(Transformation, transformation_id)
    if not transformation:
        raise HTTPException(status_code=404, detail=f"Transformation with ID {transformation_id} not found")
    if transformation.Deleted:
        raise HTTPException(status_code=404, detail=f"Transformation with ID {transformation_id} is deleted")

    # Get related transformation attributes
    query = select(TransformationAttribute).where(
        TransformationAttribute.TransformationId == transformation_id, TransformationAttribute.Deleted == False
    )
    result = await session.execute(query)
    transformation_attributes = result.scalars().all()

    # Initialize the source and target attributes
    source_attribute_dtos = []
    target_attribute_dto = None

    for transformation_attribute in transformation_attributes:
        # Fetch attribute and entity names using the service methods
        attribute_data = await get_attribute_dto_by_id(session, transformation_attribute.AttributeId)

        # Create the TransformationAttributeDTO
        attribute_dto = TransformationAttributeDTO(
            AttributeId=transformation_attribute.AttributeId,
            EntityId=transformation_attribute.EntityId,
            # AttributeName=attribute_data.Name,
            AttributeType=transformation_attribute.AttributeType,
            Notes=transformation_attribute.Notes,
            CreationDate=transformation_attribute.CreationDate,
            ActivationDate=transformation_attribute.ActivationDate,
            DeprecationDate=transformation_attribute.DeprecationDate,
            Contributor=transformation_attribute.Contributor,
            ContributorOrganization=transformation_attribute.ContributorOrganization,
            EntityIdPath=transformation_attribute.EntityIdPath,
        )

        # Assign based on the attribute type (Source or Target)
        if transformation_attribute.AttributeType == "Source":
            source_attribute_dtos.append(attribute_dto)
        else:
            target_attribute_dto = attribute_dto

    # Build the TransformationDTO
    transformation_dto = TransformationDTO(
        Id=transformation.Id,
        TransformationGroupId=transformation.TransformationGroupId,
        Name=transformation.Name,
        ExpressionLanguage=transformation.ExpressionLanguage,
        Expression=transformation.Expression,
        Notes=transformation.Notes,
        Alignment=transformation.Alignment,
        CreationDate=transformation.CreationDate,
        ActivationDate=transformation.ActivationDate,
        DeprecationDate=transformation.DeprecationDate,
        Contributor=transformation.Contributor,
        ContributorOrganization=transformation.ContributorOrganization,
        SourceAttributes=source_attribute_dtos,
        TargetAttribute=target_attribute_dto,
    )

    return transformation_dto


async def update_transformation(session: AsyncSession, transformation_id: int, data: UpdateTransformationDTO) -> dict:
    # Validate transformation
    transformation = await session.get(Transformation, transformation_id)
    if not transformation:
        raise HTTPException(status_code=404, detail=f"Transformation with ID {transformation_id} not found")
    if transformation.Deleted:
        raise HTTPException(status_code=404, detail=f"Transformation with ID {id} is deleted")

    # Validate transformation group
    transformation_group = await get_transformation_group_by_id(session=session, id=data.TransformationGroupId)
    if transformation.TransformationGroupId != transformation_group.Id:
        raise HTTPException(
            status_code=400,
            detail=f"Transformation with ID {transformation_id} does not belong to the specified transformation group.",
        )

    for key, value in data.dict().items():
        if key in transformation.__dict__ and (value is not None or key in data.model_fields_set):
            setattr(transformation, key, value)
    session.add(transformation)

    source_data_model = await check_datamodel_by_id(session=session, id=transformation_group.SourceDataModelId)
    target_data_model = await check_datamodel_by_id(session=session, id=transformation_group.TargetDataModelId)

    # Update the source attributes
    source_attributes = []
    if data.SourceAttributes:
        update_source_attribute_ids = []
        for attr in data.SourceAttributes:
            # Validate source attribute
            await check_transformation_attribute(
                session=session, anchor_data_model=source_data_model, id_path=attr.EntityIdPath
            )

            update_source_attribute_ids.append(attr.AttributeId)

            # If attribute exists, update its attribute transformation
            query = select(TransformationAttribute).where(
                TransformationAttribute.TransformationId == transformation_id,
                TransformationAttribute.AttributeId == attr.AttributeId,
                TransformationAttribute.AttributeType == "Source",
                TransformationAttribute.Deleted == False,
            )
            result = await session.execute(query)
            transformation_attribute_result = result.scalars().first()
            if transformation_attribute_result:
                existing_transformation_attribute = await session.get(
                    TransformationAttribute, transformation_attribute_result.Id
                )
                for key, value in attr.dict(exclude_unset=True).items():
                    setattr(existing_transformation_attribute, key, value)
                source_attributes.append(TransformationAttributeDTO.from_orm(existing_transformation_attribute))
            else:  # create a new attribute transformation
                source_attribute = TransformationAttribute(
                    TransformationId=transformation.Id,
                    AttributeId=attr.AttributeId,
                    EntityId=attr.EntityId,
                    AttributeType="Source",
                    Notes=attr.Notes,
                    CreationDate=attr.CreationDate,
                    ActivationDate=attr.ActivationDate,
                    DeprecationDate=attr.DeprecationDate,
                    Contributor=attr.Contributor,
                    ContributorOrganization=attr.ContributorOrganization,
                    EntityIdPath=attr.EntityIdPath,
                )
                source_attributes.append(TransformationAttributeDTO.from_orm(source_attribute))
                session.add(source_attribute)

        # Delete source attributes that are not in the update list
        query = select(TransformationAttribute).where(
            TransformationAttribute.TransformationId == transformation_id,
            TransformationAttribute.AttributeType == "Source",
            TransformationAttribute.Deleted == False,
            TransformationAttribute.AttributeId.notin_(update_source_attribute_ids),
        )
        result = await session.execute(query)
        source_attribute_transformations_to_delete = result.scalars().all()
        for attr in source_attribute_transformations_to_delete:
            session_attr_to_delete = await session.get(TransformationAttribute, attr.Id)
            session_attr_to_delete.Deleted = True
            session.add(session_attr_to_delete)
    else:
        # Query for existing source attributes to include in output
        query = select(TransformationAttribute).where(
            TransformationAttribute.TransformationId == transformation_id,
            TransformationAttribute.AttributeType == "Source",
            TransformationAttribute.Deleted == False,
        )
        result = await session.execute(query)
        source_attribute_results = result.scalars().all()
        source_attributes = [TransformationAttributeDTO.from_orm(attr) for attr in source_attribute_results]

    # Update the target attributes
    target_query = select(TransformationAttribute).where(
        TransformationAttribute.TransformationId == transformation_id,
        TransformationAttribute.AttributeType == "Target",
        TransformationAttribute.Deleted == False,
    )
    target_result = await session.execute(target_query)
    target_transformation_attribute = target_result.scalars().first()

    if data.TargetAttribute:
        # Validate target attribute
        await check_transformation_attribute(
            session=session, anchor_data_model=target_data_model, id_path=data.TargetAttribute.EntityIdPath
        )

        # Update target attribute
        if target_transformation_attribute:
            target_attribute = await session.get(TransformationAttribute, target_transformation_attribute.Id)
            for key, value in data.TargetAttribute.dict(exclude_unset=True).items():
                if value:
                    setattr(target_attribute, key, value)
            session.add(target_attribute)
            target_transformation_attribute = TransformationAttributeDTO.from_orm(target_attribute)
        else:  # create a new target attribute transformation
            target_attribute = TransformationAttribute(
                TransformationId=transformation.Id,
                AttributeId=data.TargetAttribute.AttributeId,
                EntityId=data.TargetAttribute.EntityId,
                AttributeType="Target",
                Notes=data.TargetAttribute.Notes,
                CreationDate=data.TargetAttribute.CreationDate,
                ActivationDate=data.TargetAttribute.ActivationDate,
                DeprecationDate=data.TargetAttribute.DeprecationDate,
                Contributor=data.TargetAttribute.Contributor,
                ContributorOrganization=data.TargetAttribute.ContributorOrganization,
                EntityIdPath=data.TargetAttribute.EntityIdPath,
            )
            session.add(target_attribute)
            target_transformation_attribute = TransformationAttributeDTO.from_orm(target_attribute)

    await session.commit()
    return TransformationDTO(
        Id=transformation.Id,
        TransformationGroupId=transformation.TransformationGroupId,
        Name=transformation.Name,
        ExpressionLanguage=transformation.ExpressionLanguage,
        Expression=transformation.Expression,
        Notes=transformation.Notes,
        Alignment=transformation.Alignment,
        CreationDate=transformation.CreationDate,
        ActivationDate=transformation.ActivationDate,
        DeprecationDate=transformation.DeprecationDate,
        Contributor=transformation.Contributor,
        ContributorOrganization=transformation.ContributorOrganization,
        SourceAttributes=source_attributes,
        TargetAttribute=target_transformation_attribute,
    )


async def soft_delete_transformation_by_id(session: AsyncSession, transformation_id: int) -> dict:
    # Check if the transformation exists
    transformation = await session.get(Transformation, transformation_id)
    if not transformation:
        raise HTTPException(status_code=404, detail=f"Transformation with ID {transformation_id} not found")
    if transformation.Deleted:
        raise HTTPException(status_code=404, detail=f"Transformation with ID {transformation_id} is deleted")

    # Delete related TransformationAttributes
    query = select(TransformationAttribute).where(
        TransformationAttribute.TransformationId == transformation_id, TransformationAttribute.Deleted == False
    )
    result = await session.execute(query)
    attributes = result.scalars().all()

    for attribute in attributes:
        attribute.Deleted = True
        session.add(attribute)

    # Delete the transformation
    transformation.Deleted = True
    session.add(transformation)
    await session.commit()

    return {"message": f"Transformation with ID {transformation_id} and its attributes deleted successfully"}


async def get_paginated_all_transformations(
    session: AsyncSession,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    source_data_model_id: int = None,
    target_data_model_id: int = None,
):
    transformations_dtos: list[GetALLTransformationsDTO] = []
    # Query to count total transformations for pagination
    total_query = (
        select(func.count(Transformation.Id))
        .join(TransformationGroup, TransformationGroup.Id == Transformation.TransformationGroupId)
        .where(
            and_(
                Transformation.Deleted == False,
                TransformationGroup.Deleted == False,
                (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
            )
        )
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    if pagination:
        transformations_query = (
            select(
                TransformationGroup.Id.label("TransformationGroupId"),
                TransformationGroup.SourceDataModelId.label("SourceDataModelId"),
                TransformationGroup.TargetDataModelId.label("TargetDataModelId"),
                TransformationGroup.Name.label("TransformationGroupName"),
                TransformationGroup.GroupVersion.label("TransformationGroupVersion"),
                TransformationGroup.Description.label("TransformationGroupDescription"),
                TransformationGroup.Notes.label("TransformationGroupNotes"),
                Transformation.Id.label("TransformationId"),
                Transformation.Expression.label("TransformationExpression"),
                Transformation.ExpressionLanguage.label("TransformationExpressionLanguage"),
                Transformation.Notes.label("TransformationNotes"),
                Transformation.Alignment.label("TransformationAlignment"),
                Transformation.CreationDate.label("TransformationCreationDate"),
                Transformation.ActivationDate.label("TransformationActivationDate"),
                Transformation.DeprecationDate.label("TransformationDeprecationDate"),
                Transformation.Contributor.label("TransformationContributor"),
                Transformation.ContributorOrganization.label("TransformationContributorOrganization"),
            )
            .join(Transformation, TransformationGroup.Id == Transformation.TransformationGroupId)
            .where(
                and_(
                    Transformation.Deleted == False,
                    TransformationGroup.Deleted == False,
                    (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                    (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
                )
            )
            .order_by(Transformation.TransformationGroupId, Transformation.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        transformations_query = (
            select(
                TransformationGroup.Id.label("TransformationGroupId"),
                TransformationGroup.SourceDataModelId.label("SourceDataModelId"),
                TransformationGroup.TargetDataModelId.label("TargetDataModelId"),
                TransformationGroup.Name.label("TransformationGroupName"),
                TransformationGroup.GroupVersion.label("TransformationGroupVersion"),
                TransformationGroup.Description.label("TransformationGroupDescription"),
                TransformationGroup.Notes.label("TransformationGroupNotes"),
                Transformation.Id.label("TransformationId"),
                Transformation.Expression.label("TransformationExpression"),
                Transformation.ExpressionLanguage.label("TransformationExpressionLanguage"),
                Transformation.Notes.label("TransformationNotes"),
                Transformation.Alignment.label("TransformationAlignment"),
                Transformation.CreationDate.label("TransformationCreationDate"),
                Transformation.ActivationDate.label("TransformationActivationDate"),
                Transformation.DeprecationDate.label("TransformationDeprecationDate"),
                Transformation.Contributor.label("TransformationContributor"),
                Transformation.ContributorOrganization.label("TransformationContributorOrganization"),
            )
            .join(Transformation, TransformationGroup.Id == Transformation.TransformationGroupId)
            .where(
                and_(
                    Transformation.Deleted == False,
                    TransformationGroup.Deleted == False,
                    (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                    (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
                )
            )
            .order_by(Transformation.TransformationGroupId, Transformation.Id)
        )

    result = await session.execute(transformations_query)
    transformations = result.fetchall()

    for transformation in transformations:
        # Get related transformation attributes
        query = select(TransformationAttribute).where(
            TransformationAttribute.TransformationId == transformation.TransformationId,
            TransformationAttribute.Deleted == False,
        )
        result = await session.execute(query)
        transformation_attributes = result.scalars().all()

        # Initialize the source and target attributes
        source_attribute_dtos = []
        target_attribute_dto = None

        for transformation_attribute in transformation_attributes:
            # Fetch attribute and entity names using the service methods
            attribute_data = await get_attribute_dto_by_id(session, transformation_attribute.AttributeId)
            # entity = await get_entity_by_id(session, attribute.EntityId)
            query = select(EntityAttributeAssociation.EntityId).where(
                EntityAttributeAssociation.AttributeId == transformation_attribute.AttributeId,
                EntityAttributeAssociation.Deleted == False,
            )
            result = await session.execute(query)
            entity_id = result.scalars().first()

            # Create the TransformationAttributeDTO
            attribute_dto = TransformationAttributeDTO(
                AttributeId=transformation_attribute.AttributeId,
                AttributeName=attribute_data.Name,  # Populating the name using service
                EntityId=entity_id,
                # EntityName=entity.Name,  # Populating the entity name using service
                AttributeType=transformation_attribute.AttributeType,
                Notes=transformation_attribute.Notes,
                CreationDate=transformation_attribute.CreationDate,
                ActivationDate=transformation_attribute.ActivationDate,
                DeprecationDate=transformation_attribute.DeprecationDate,
                Contributor=transformation_attribute.Contributor,
                ContributorOrganization=transformation_attribute.ContributorOrganization,
                EntityIdPath=transformation_attribute.EntityIdPath,
            )

            # Assign based on the attribute type (Source or Target)
            if transformation_attribute.AttributeType == "Source":
                source_attribute_dtos.append(attribute_dto)
            else:
                target_attribute_dto = attribute_dto

        # Build the TransformationDTO
        transformation_dto = GetALLTransformationsDTO(
            TransformationGroupId=transformation.TransformationGroupId,
            SourceDataModelId=transformation.SourceDataModelId,
            TargetDataModelId=transformation.TargetDataModelId,
            TransformationGroupName=transformation.TransformationGroupName,
            TransformationGroupVersion=transformation.TransformationGroupVersion,
            TransformationGroupDescription=transformation.TransformationGroupDescription,
            TransformationGroupNotes=transformation.TransformationGroupNotes,
            TransformationId=transformation.TransformationId,
            TransformationExpression=transformation.TransformationExpression,
            TransformationExpressionLanguage=transformation.TransformationExpressionLanguage,
            TransformationNotes=transformation.TransformationNotes,
            TransformationAlignment=transformation.TransformationAlignment,
            TransformationCreationDate=transformation.TransformationCreationDate,
            TransformationActivationDate=transformation.TransformationActivationDate,
            TransformationDeprecationDate=transformation.TransformationDeprecationDate,
            TransformationContributor=transformation.TransformationContributor,
            TransformationContributorOrganization=transformation.TransformationContributorOrganization,
            TransformationSourceAttributes=source_attribute_dtos,
            TransformationTargetAttribute=target_attribute_dto,
        )
        transformations_dtos.append(transformation_dto)

    return total_count, transformations_dtos


async def get_paginated_all_transformations_for_an_attribute(
    session: AsyncSession,
    attribute_id: int,
    attribute_as_source: bool = True,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    source_data_model_id: int = None,
    target_data_model_id: int = None,
):
    if attribute_as_source and not source_data_model_id:
        raise HTTPException(
            status_code=400,
            detail=f"Missing : source_data_model_id. To get all the transformation where provided attribute with id {attribute_id} is a source, source data model id is required.",
        )

    if not attribute_as_source and not target_data_model_id:
        raise HTTPException(
            status_code=400,
            detail=f"Missing : target_data_model_id. To get all the transformation where provided attribute with id {attribute_id} is a target, target data model id is required.",
        )

    transformations_dtos: list[GetALLTransformationsDTO] = []
    # Query to count total transformations for pagination
    total_query = (
        select(func.count(TransformationAttribute.Id))
        .join(Transformation, Transformation.Id == TransformationAttribute.TransformationId)
        .join(TransformationGroup, TransformationGroup.Id == Transformation.TransformationGroupId)
        .where(
            and_(
                TransformationAttribute.Deleted == False,
                Transformation.Deleted == False,
                TransformationGroup.Deleted == False,
                (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
                (TransformationAttribute.AttributeId == attribute_id),
            )
        )
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    if pagination:
        transformations_query = (
            select(
                TransformationGroup.Id.label("TransformationGroupId"),
                TransformationGroup.SourceDataModelId.label("SourceDataModelId"),
                TransformationGroup.TargetDataModelId.label("TargetDataModelId"),
                TransformationGroup.Name.label("TransformationGroupName"),
                TransformationGroup.GroupVersion.label("TransformationGroupVersion"),
                TransformationGroup.Description.label("TransformationGroupDescription"),
                TransformationGroup.Notes.label("TransformationGroupNotes"),
                Transformation.Id.label("TransformationId"),
                Transformation.Expression.label("TransformationExpression"),
                Transformation.ExpressionLanguage.label("TransformationExpressionLanguage"),
                Transformation.Notes.label("TransformationNotes"),
                Transformation.Alignment.label("TransformationAlignment"),
                Transformation.CreationDate.label("TransformationCreationDate"),
                Transformation.ActivationDate.label("TransformationActivationDate"),
                Transformation.DeprecationDate.label("TransformationDeprecationDate"),
                Transformation.Contributor.label("TransformationContributor"),
                Transformation.ContributorOrganization.label("TransformationContributorOrganization"),
            )
            .join(Transformation, TransformationGroup.Id == Transformation.TransformationGroupId)
            .join(TransformationAttribute, Transformation.Id == TransformationAttribute.TransformationId)
            .where(
                and_(
                    Transformation.Deleted == False,
                    TransformationGroup.Deleted == False,
                    TransformationAttribute.Deleted == False,
                    (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                    (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
                    (TransformationAttribute.AttributeId == attribute_id),
                )
            )
            .order_by(Transformation.TransformationGroupId, Transformation.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        transformations_query = (
            select(
                TransformationGroup.Id.label("TransformationGroupId"),
                TransformationGroup.SourceDataModelId.label("SourceDataModelId"),
                TransformationGroup.TargetDataModelId.label("TargetDataModelId"),
                TransformationGroup.Name.label("TransformationGroupName"),
                TransformationGroup.GroupVersion.label("TransformationGroupVersion"),
                TransformationGroup.Description.label("TransformationGroupDescription"),
                TransformationGroup.Notes.label("TransformationGroupNotes"),
                Transformation.Expression.label("TransformationExpression"),
                Transformation.ExpressionLanguage.label("TransformationExpressionLanguage"),
                Transformation.Notes.label("TransformationNotes"),
                Transformation.Alignment.label("TransformationAlignment"),
                Transformation.CreationDate.label("TransformationCreationDate"),
                Transformation.ActivationDate.label("TransformationActivationDate"),
                Transformation.DeprecationDate.label("TransformationDeprecationDate"),
                Transformation.Contributor.label("TransformationContributor"),
                Transformation.ContributorOrganization.label("TransformationContributorOrganization"),
            )
            .join(Transformation, TransformationGroup.Id == Transformation.TransformationGroupId)
            .join(TransformationAttribute, Transformation.Id == TransformationAttribute.TransformationId)
            .where(
                and_(
                    Transformation.Deleted == False,
                    TransformationGroup.Deleted == False,
                    TransformationAttribute.Deleted == False,
                    (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                    (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
                    (TransformationAttribute.AttributeId == attribute_id),
                )
            )
            .order_by(Transformation.TransformationGroupId, Transformation.Id)
        )

    result = await session.execute(transformations_query)
    transformations = result.fetchall()

    for transformation in transformations:
        # Get related transformation attributes
        query = select(TransformationAttribute).where(
            TransformationAttribute.TransformationId == transformation.TransformationId,
            TransformationAttribute.Deleted == False,
        )
        result = await session.execute(query)
        transformation_attributes = result.scalars().all()

        # Initialize the source and target attributes
        source_attribute_dtos = []
        target_attribute_dto = None

        for transformation_attribute in transformation_attributes:
            # Fetch attribute and entity names using the service methods
            attribute_data = await get_attribute_dto_by_id(session, transformation_attribute.AttributeId)
            # entity = await get_entity_by_id(session, attribute.EntityId)
            query = select(EntityAttributeAssociation.EntityId).where(
                EntityAttributeAssociation.AttributeId == transformation_attribute.AttributeId,
                EntityAttributeAssociation.Deleted == False,
            )
            result = await session.execute(query)
            entity_id = result.scalars().first()

            # Create the TransformationAttributeDTO
            attribute_dto = TransformationAttributeDTO(
                AttributeId=transformation_attribute.AttributeId,
                AttributeName=attribute_data.Name,  # Populating the name using service
                EntityId=entity_id,
                # EntityName=entity.Name,  # Populating the entity name using service
                AttributeType=transformation_attribute.AttributeType,
                Notes=transformation_attribute.Notes,
                CreationDate=transformation_attribute.CreationDate,
                ActivationDate=transformation_attribute.ActivationDate,
                DeprecationDate=transformation_attribute.DeprecationDate,
                Contributor=transformation_attribute.Contributor,
                ContributorOrganization=transformation_attribute.ContributorOrganization,
                EntityIdPath=transformation_attribute.EntityIdPath,
            )

            # Assign based on the attribute type (Source or Target)
            if transformation_attribute.AttributeType == "Source":
                source_attribute_dtos.append(attribute_dto)
            else:
                target_attribute_dto = attribute_dto

        # Build the TransformationDTO
        transformation_dto = GetALLTransformationsDTO(
            TransformationGroupId=transformation.TransformationGroupId,
            SourceDataModelId=transformation.SourceDataModelId,
            TargetDataModelId=transformation.TargetDataModelId,
            TransformationGroupName=transformation.TransformationGroupName,
            TransformationGroupVersion=transformation.TransformationGroupVersion,
            TransformationGroupDescription=transformation.TransformationGroupDescription,
            TransformationGroupNotes=transformation.TransformationGroupNotes,
            TransformationId=transformation.TransformationId,
            TransformationExpression=transformation.TransformationExpression,
            TransformationExpressionLanguage=transformation.TransformationExpressionLanguage,
            TransformationNotes=transformation.TransformationNotes,
            TransformationAlignment=transformation.TransformationAlignment,
            TransformationCreationDate=transformation.TransformationCreationDate,
            TransformationActivationDate=transformation.TransformationActivationDate,
            TransformationDeprecationDate=transformation.TransformationDeprecationDate,
            TransformationContributor=transformation.TransformationContributor,
            TransformationContributorOrganization=transformation.TransformationContributorOrganization,
            TransformationSourceAttributes=source_attribute_dtos,
            TransformationTargetAttribute=target_attribute_dto,
        )
        transformations_dtos.append(transformation_dto)

    return total_count, transformations_dtos


# Transformation Group APIs


async def get_paginated_transformations_groups(
    session: AsyncSession,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    source_data_model_id: int = None,
    target_data_model_id: int = None,
    exportable: bool = False,
):
    transformations_group_dtos: list[TransformationGroupDTO] = []
    # Query to count total transformations for pagination
    total_query = select(func.count(TransformationGroup.Id)).where(
        and_(
            TransformationGroup.Deleted == False,
            (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
            (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
        )
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    if pagination:
        transformations_group_query = (
            select(TransformationGroup)
            .where(
                and_(
                    TransformationGroup.Deleted == False,
                    (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                    (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
                )
            )
            .order_by(TransformationGroup.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        transformations_group_query = (
            select(TransformationGroup)
            .where(
                and_(
                    TransformationGroup.Deleted == False,
                    (TransformationGroup.SourceDataModelId == source_data_model_id if source_data_model_id else True),
                    (TransformationGroup.TargetDataModelId == target_data_model_id if target_data_model_id else True),
                )
            )
            .order_by(TransformationGroup.Id)
        )

    result = await session.execute(transformations_group_query)
    transformations_group = result.scalars().all()
    logger.info(f"transformations_group:{transformations_group}")
    # transformations_group_dtos = [TransformationGroupDTO.from_orm(group) for group in transformations_group]
    transformations_group_dtos = []
    for group in transformations_group:
        transformation_group_dto = TransformationGroupDTO.from_orm(group)
        source_data_model = await check_datamodel_by_id(session=session, id=transformation_group_dto.SourceDataModelId)
        target_data_model = await check_datamodel_by_id(session=session, id=transformation_group_dto.TargetDataModelId)
        transformation_group_dto.SourceDataModelName = source_data_model.Name
        transformation_group_dto.TargetDataModelName = target_data_model.Name
        if exportable:
            # Add portable (name, version, org) refs alongside the non-portable IDs.
            transformation_group_dto.SourceDataModel = DataModelRefDTO(
                name=source_data_model.Name,
                version=source_data_model.DataModelVersion,
                contributorOrganization=source_data_model.ContributorOrganization,
            )
            transformation_group_dto.TargetDataModel = DataModelRefDTO(
                name=target_data_model.Name,
                version=target_data_model.DataModelVersion,
                contributorOrganization=target_data_model.ContributorOrganization,
            )
        transformations_group_dtos.append(transformation_group_dto)

    return total_count, transformations_group_dtos


async def get_transformation_group_by_id(session: AsyncSession, id: int):
    transformation_group = await session.get(TransformationGroup, id)
    if not transformation_group:
        raise HTTPException(status_code=404, detail=f"Transformation group with id {id}  not found")
    if transformation_group.Deleted:
        raise HTTPException(status_code=404, detail=f"Transformation group with ID {id} is deleted")
    # return TransformationGroupDTO.from_orm(transformation_group)
    return transformation_group


async def _resolve_entity_id_path_to_named_path(
    session: AsyncSession, id_path: str, cache: dict[tuple[str, int], str]
) -> str:
    from lif.datatypes.mdr_sql_model import Attribute, Entity

    ids = parse_transformation_path(id_path)
    segments: list[str] = []

    for i, raw_id in enumerate(ids):
        is_last = i == len(ids) - 1
        if not is_last and raw_id < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to export - invalid path '{id_path}': non-terminal ID '{raw_id}' must be positive",
            )
        is_attribute = is_last and raw_id < 0
        cleaned_id = abs(raw_id)
        cache_key = ("attribute" if is_attribute else "entity", cleaned_id)

        if cache_key not in cache:
            record = await session.get(Attribute, cleaned_id) if is_attribute else await session.get(Entity, cleaned_id)
            record_type = cache_key[0].capitalize()
            if not record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Unable to export - {record_type} ID {cleaned_id} in path '{id_path}' not found",
                )
            if record.Deleted == True:
                raise HTTPException(
                    status_code=404,
                    detail=f"Unable to export - {record_type} ID {cleaned_id} in path '{id_path}' is deleted",
                )
            record_type_flag = "~" if is_attribute else ""
            cache[cache_key] = f"{record.DataModelId}:{record_type_flag}{record.UniqueName}"

        segments.append(cache[cache_key])

    return ",".join(segments)


async def get_paginated_transformations_for_a_group(
    session: AsyncSession,
    group_id: int,
    offset: int = 0,
    limit: int = 10,
    pagination: bool = True,
    make_exportable: bool = False,  # Only is honored when pagination is False and this is set to True.
):
    transformation_group = await get_transformation_group_by_id(session=session, id=group_id)
    transformation_group_dto = TransformationGroupDTO.from_orm(transformation_group)
    source_data_model = await check_datamodel_by_id(session=session, id=transformation_group_dto.SourceDataModelId)
    target_data_model = await check_datamodel_by_id(session=session, id=transformation_group_dto.TargetDataModelId)
    transformation_group_dto.SourceDataModelName = source_data_model.Name
    transformation_group_dto.TargetDataModelName = target_data_model.Name

    transformations_dtos: list[TransformationDTO] = []

    # Query to count total transformations for pagination
    total_query = (
        select(func.count(Transformation.Id))
        .where(Transformation.TransformationGroupId == group_id)
        .where(Transformation.Deleted == False)
    )
    if not pagination and make_exportable:
        total_query = total_query.where(Transformation.ExpressionLanguage == ExpressionLanguageType.JSONata)

    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    if pagination:
        transformations_query = (
            select(Transformation)
            .where(Transformation.TransformationGroupId == group_id, Transformation.Deleted == False)
            .order_by(Transformation.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        where_expressions = [Transformation.TransformationGroupId == group_id, Transformation.Deleted == False]
        if make_exportable:
            where_expressions.append(Transformation.ExpressionLanguage == ExpressionLanguageType.JSONata)
        transformations_query = select(Transformation).where(*where_expressions).order_by(Transformation.Id)

    result = await session.execute(transformations_query)
    transformations = result.scalars().all()
    entity_attribute_cache: dict[tuple[str, int], str] = {}
    for transformation in transformations:
        # Get related transformation attributes
        query = select(TransformationAttribute).where(
            TransformationAttribute.TransformationId == transformation.Id, TransformationAttribute.Deleted == False
        )
        result = await session.execute(query)
        transformation_attributes = result.scalars().all()

        # Initialize the source and target attributes
        source_attribute_dtos = []
        target_attribute_dto = None

        for transformation_attribute in transformation_attributes:
            # Fetch attribute and entity names using the service methods
            attribute_data = await get_attribute_dto_by_id(session, transformation_attribute.AttributeId)
            # entity = await get_entity_by_id(session, attribute.EntityId)
            query = select(EntityAttributeAssociation.EntityId).where(
                EntityAttributeAssociation.AttributeId == transformation_attribute.AttributeId,
                EntityAttributeAssociation.Deleted == False,
            )
            result = await session.execute(query)
            entity_id = result.scalars().first()

            # Create the TransformationAttributeDTO
            attribute_dto = TransformationAttributeDTO(
                AttributeId=transformation_attribute.AttributeId,
                AttributeName=attribute_data.Name,  # Populating the name using service
                EntityId=entity_id,
                # EntityName=entity.Name,  # Populating the entity name using service
                AttributeType=transformation_attribute.AttributeType,
                Notes=transformation_attribute.Notes,
                CreationDate=transformation_attribute.CreationDate,
                ActivationDate=transformation_attribute.ActivationDate,
                DeprecationDate=transformation_attribute.DeprecationDate,
                Contributor=transformation_attribute.Contributor,
                ContributorOrganization=transformation_attribute.ContributorOrganization,
                EntityIdPath=transformation_attribute.EntityIdPath,
            )

            if make_exportable:
                attribute_dto.EntityIdPath = await _resolve_entity_id_path_to_named_path(
                    session=session, id_path=transformation_attribute.EntityIdPath, cache=entity_attribute_cache
                )

            # Assign based on the attribute type (Source or Target)
            if transformation_attribute.AttributeType == "Source":
                source_attribute_dtos.append(attribute_dto)
            else:
                target_attribute_dto = attribute_dto

        # Build the TransformationDTO
        transformation_dto = TransformationDTO(
            Id=transformation.Id,
            TransformationGroupId=group_id,
            Name=transformation.Name,
            ExpressionLanguage=transformation.ExpressionLanguage,
            Expression=transformation.Expression,
            Notes=transformation.Notes,
            Alignment=transformation.Alignment,
            CreationDate=transformation.CreationDate,
            ActivationDate=transformation.ActivationDate,
            DeprecationDate=transformation.DeprecationDate,
            Contributor=transformation.Contributor,
            ContributorOrganization=transformation.ContributorOrganization,
            SourceAttributes=source_attribute_dtos,  # Source attribute DTO
            TargetAttribute=target_attribute_dto,  # Target attribute DTO
        )
        transformations_dtos.append(transformation_dto)
    transformation_group_dto.Transformations = transformations_dtos
    return total_count, transformation_group_dto


async def get_transformation_group_for_source_and_target(
    session: AsyncSession, source_data_model_id: int, target_data_model_id: int
):
    # Validate that requested data models exist and are not deleted
    await check_datamodel_by_id(session=session, id=source_data_model_id)
    await check_datamodel_by_id(session=session, id=target_data_model_id)

    query = select(TransformationGroup).where(
        TransformationGroup.SourceDataModelId == source_data_model_id,
        TransformationGroup.TargetDataModelId == target_data_model_id,
        TransformationGroup.Deleted == False,
    )
    result = await session.execute(query)
    transformation_groups = result.scalars().all()
    transformation_group_dtos: List[TransformationGroupDTO] = []
    for group in transformation_groups:
        transformation_group_dto = TransformationGroupDTO.from_orm(group)
        transformation_group_dtos.append(transformation_group_dto)
    return transformation_group_dtos


async def create_transformation_group(session: AsyncSession, data: CreateTransformationGroupDTO, commit: bool = True):
    # When commit=False the caller owns the transaction boundary (used by the group import so the
    # whole import is one atomic transaction); we flush to obtain the generated ID but never commit.
    # Checking if data models exist or not
    await check_datamodel_by_id(session=session, id=data.SourceDataModelId)
    await check_datamodel_by_id(session=session, id=data.TargetDataModelId)

    # Check if transformation group exists. Use `IS NOT TRUE` (not `== False`) so a legacy row with
    # Deleted = NULL counts as active — matching the partial unique index
    # ux_transformationsgroup_model_id_version_active (WHERE "Deleted" IS NOT TRUE). Otherwise this
    # check would miss a NULL-deleted duplicate that the index still rejects, surfacing as a
    # confusing IntegrityError instead of this clear 400.
    existing_group = await session.execute(
        select(TransformationGroup).where(
            TransformationGroup.SourceDataModelId == data.SourceDataModelId,
            TransformationGroup.TargetDataModelId == data.TargetDataModelId,
            TransformationGroup.GroupVersion == data.GroupVersion,
            TransformationGroup.Deleted.isnot(True),
        )
    )
    if existing_group.scalars().first():
        raise HTTPException(
            status_code=400,
            detail=f"Transformation group already exists for SourceDataModelId {data.SourceDataModelId}, TargetDataModelId {data.TargetDataModelId}, GroupVersion {data.GroupVersion}",
        )

    transformation_group = TransformationGroup(
        SourceDataModelId=data.SourceDataModelId,
        TargetDataModelId=data.TargetDataModelId,
        GroupVersion=data.GroupVersion,
        Name=data.Name,
        Notes=data.Notes,
        Description=data.Description,
        CreationDate=data.CreationDate,
        ActivationDate=data.ActivationDate,
        DeprecationDate=data.DeprecationDate,
        Contributor=data.Contributor,
        ContributorOrganization=data.ContributorOrganization,
    )
    session.add(transformation_group)
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(transformation_group)
    transformation_group_dto = TransformationGroupDTO.from_orm(transformation_group)

    return transformation_group_dto


async def find_transformation_group_by_triplet(
    session: AsyncSession, source_id: int, target_id: int, group_version: str, include_deleted: bool = True
):
    """
    Returns a TransformationGroup matching the provided (source, target, version).
    If include_deleted is False, only non-deleted groups are considered.
    """
    query = select(TransformationGroup).where(
        and_(
            TransformationGroup.SourceDataModelId == source_id,
            TransformationGroup.TargetDataModelId == target_id,
            TransformationGroup.GroupVersion == group_version,
        )
    )
    if not include_deleted:
        # `IS NOT TRUE` (not `== False`) so a Deleted = NULL row counts as active, matching the
        # partial unique index ux_transformationsgroup_model_id_version_active. This keeps the import
        # flow's edit-vs-create decision consistent with what the DB will actually enforce.
        query = query.where(TransformationGroup.Deleted.isnot(True))
    result = await session.execute(query)
    return result.scalars().first()


async def create_multiple_transformations_for_a_group(
    session: AsyncSession, transformation_group_id: int, data: List[CreateTransformationWithTransformationGroupDTO]
):
    # Checking if data models exist or not
    transformation_group = await get_transformation_group_by_id(session=session, id=transformation_group_id)
    transformation_group_dto = TransformationGroupDTO.from_orm(transformation_group)
    transformation_list: List[TransformationDTO] = []
    for transformation in data:
        create_transformation_dto = CreateTransformationDTO(
            **transformation.dict(), TransformationGroupId=transformation_group_id
        )
        transformation_dto = await create_transformation(session=session, data=create_transformation_dto)
        transformation_list.append(transformation_dto)
    transformation_group_dto.Transformations = transformation_list
    return transformation_group_dto


async def update_transformation_group(
    session: AsyncSession, transformation_group_id: int, data: UpdateTransformationGroupDTO
):
    transformation_group = await session.get(TransformationGroup, transformation_group_id)
    if not transformation_group:
        raise HTTPException(
            status_code=404, detail=f"Transformation group with id {transformation_group_id}  not found"
        )
    if transformation_group.Deleted:
        raise HTTPException(
            status_code=404, detail=f"Transformation group with ID {transformation_group_id} is deleted"
        )

    # Checking if data models exist or not
    if data.SourceDataModelId:
        await check_datamodel_by_id(session=session, id=data.SourceDataModelId)
    if data.TargetDataModelId:
        await check_datamodel_by_id(session=session, id=data.TargetDataModelId)

    # Check that these updates won't make this transformation group a duplicate with another
    result = await session.execute(
        select(TransformationGroup).where(
            TransformationGroup.SourceDataModelId == data.SourceDataModelId,
            TransformationGroup.TargetDataModelId == data.TargetDataModelId,
            TransformationGroup.GroupVersion == data.GroupVersion,
            TransformationGroup.Deleted == False,
        )
    )
    existing_group = result.scalars().first()
    if existing_group and existing_group.Id != transformation_group_id:
        raise HTTPException(
            status_code=400,
            detail=f"Transformation group already exists for SourceDataModelId {data.SourceDataModelId}, TargetDataModelId {data.TargetDataModelId}, GroupVersion {data.GroupVersion}",
        )

    # Check that these updates won't make this transformation group a duplicate with another
    result = await session.execute(
        select(TransformationGroup).where(
            TransformationGroup.SourceDataModelId == data.SourceDataModelId,
            TransformationGroup.TargetDataModelId == data.TargetDataModelId,
            TransformationGroup.GroupVersion == data.GroupVersion,
            TransformationGroup.Deleted == False,
        )
    )
    existing_group = result.scalars().first()
    if existing_group and existing_group.Id != transformation_group_id:
        raise HTTPException(
            status_code=400,
            detail=f"Transformation group already exists for SourceDataModelId {data.SourceDataModelId}, TargetDataModelId {data.TargetDataModelId}, GroupVersion {data.GroupVersion}",
        )

    for key, value in data.dict(exclude_unset=True).items():
        if value:
            setattr(transformation_group, key, value)
    transformation_group_dto = TransformationGroupDTO.from_orm(transformation_group)

    # actually update the group in db
    session.add(transformation_group)
    await session.commit()

    if data.Transformations:
        transformation_list: List[TransformationDTO] = []
        for transformation in data.Transformations:
            transformation.TransformationGroupId = transformation_group_id
            updated_transformation_dto = await update_transformation(
                session=session, transformation_id=transformation.Id, data=transformation
            )
            transformation_list.append(updated_transformation_dto)
        transformation_group_dto.Transformations = transformation_list

    return transformation_group_dto


async def soft_delete_transformation_group(session: AsyncSession, transformation_group_id: int) -> dict:
    # Check if the transformation exists
    transformation_group = await session.get(TransformationGroup, transformation_group_id)
    if not transformation_group:
        raise HTTPException(
            status_code=404, detail=f"Transformation group with id {transformation_group_id}  not found"
        )
    if transformation_group.Deleted:
        raise HTTPException(
            status_code=404, detail=f"Transformation group with ID {transformation_group_id} is deleted"
        )

    # Delete related TransformationAttributes
    query = select(Transformation).where(
        Transformation.TransformationGroupId == transformation_group_id, Transformation.Deleted == False
    )
    result = await session.execute(query)
    transformations = result.scalars().all()

    for transformation in transformations:
        await soft_delete_transformation_by_id(session=session, transformation_id=transformation.Id)

    # Delete the transformation
    transformation_group.Deleted = True
    session.add(transformation_group)
    await session.commit()

    return {"message": f"Transformation Group with ID {transformation_group_id} deleted successfully"}


async def get_distinct_data_models_in_transformations(session: AsyncSession) -> List[Dict[str, str]]:
    # Step 1: Query distinct SourceDataModelId and TargetDataModelId from Transformation table
    # Alias the DataModel table for the source and target
    SourceDataModel = aliased(DataModel)
    TargetDataModel = aliased(DataModel)

    query = (
        select(
            TransformationGroup.Id,
            TransformationGroup.GroupVersion,
            TransformationGroup.SourceDataModelId,
            SourceDataModel.Name.label("SourceDataModelName"),
            TransformationGroup.TargetDataModelId,
            TargetDataModel.Name.label("TargetDataModelName"),
        )
        .join(SourceDataModel, SourceDataModel.Id == TransformationGroup.SourceDataModelId)
        .join(TargetDataModel, TargetDataModel.Id == TransformationGroup.TargetDataModelId)
        .distinct()
        .where(TransformationGroup.Deleted == False)
    )

    result = await session.execute(query)
    transformation_data_models = result.fetchall()
    # Step 2: Prepare response to include both source and target data model details
    response = [
        {
            "TransformationGroupId": row.Id,
            "GroupVersion": row.GroupVersion,
            "SourceDataModelId": row.SourceDataModelId,
            "SourceDataModelName": row.SourceDataModelName,
            "TargetDataModelId": row.TargetDataModelId,
            "TargetDataModelName": row.TargetDataModelName,
        }
        for row in transformation_data_models
    ]
    return response


async def get_transformations_by_data_model_id(session: AsyncSession, data_model_id: int) -> TransformationListDTO:
    # Query for transformations where the given model is the source
    source_query = (
        select(Transformation)
        .join(TransformationGroup, TransformationGroup.Id == Transformation.TransformationGroupId)
        .where(TransformationGroup.SourceDataModelId == data_model_id)
        .where(Transformation.Deleted == False)
        .where(TransformationGroup.Deleted == False)
    )
    source_result = await session.execute(source_query)
    source_transformations = source_result.scalars().all()

    # Query for transformations where the given model is the target
    target_query = (
        select(Transformation)
        .join(TransformationGroup, TransformationGroup.Id == Transformation.TransformationGroupId)
        .where(TransformationGroup.TargetDataModelId == data_model_id)
        .where(Transformation.Deleted == False)
        .where(TransformationGroup.Deleted == False)
    )
    target_result = await session.execute(target_query)
    target_transformations = target_result.scalars().all()

    source_transformation_dto_list: list[TransformationDTO] = []
    for source in source_transformations:
        source_dto = await get_transformation_by_id(session=session, transformation_id=source.Id)
        source_transformation_dto_list.append(source_dto)

    target_transformation_dto_list: list[TransformationDTO] = []
    for target in target_transformations:
        target_dto = await get_transformation_by_id(session=session, transformation_id=target.Id)
        target_transformation_dto_list.append(target_dto)

    # Return the transformation lists
    return TransformationListDTO(
        SourceTransformations=source_transformation_dto_list, TargetTransformations=target_transformation_dto_list
    )


async def get_transformations_by_path_ids(
    session: AsyncSession, entity_id_path: str, attribute_id: int = None
) -> List[TransformationDTO]:
    # Select Transformations where TransformationAttribute.EntityIdPath == entity_id_path and TransformationAttribute.AttributeId == attribute_id
    query = (
        select(Transformation.Id)
        .join(TransformationAttribute, TransformationAttribute.TransformationId == Transformation.Id)
        .where(Transformation.Deleted == False)
        .where(TransformationAttribute.EntityIdPath == entity_id_path)
    )

    # `is not None`, not truthiness: an AttributeId of 0 is a valid filter value; `if attribute_id:`
    # would drop the filter and return transformations for ALL attributes (cf. #1006 ElementId fix).
    if attribute_id is not None:
        query = query.where(TransformationAttribute.AttributeId == attribute_id)

    result = await session.execute(query)
    transformation_ids = result.scalars().all()
    transformations = []

    for trans_id in transformation_ids:
        transformation = await get_transformation_by_id(session=session, transformation_id=trans_id)
        transformations.append(transformation)

    return transformations


# Transformation Group Import (#772)
#
# Import is the reverse of the export (#771). The export turns a numeric ``EntityIdPath``
# ("5,-12") into portable segments "{DataModelId}:{~}{UniqueName}" via
# ``_resolve_entity_id_path_to_named_path``. Import resolves those UniqueNames back to LOCAL
# entity/attribute IDs, honoring data portability: the numeric "{DataModelId}:" prefix in each
# segment is the originating model ID from whatever instance authored the file and is IGNORED —
# the only ID matched against this database is the transformation-group ID on the route, from
# which the source and target data models (the resolution anchors) are derived.


class UnmatchedPathError(Exception):
    """A portable path could not be resolved to a valid local numeric path during import."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


async def resolve_named_path(session: AsyncSession, named_path: str, anchor_data_model: DataModel) -> List[int]:
    """Resolve a portable named path to a list of signed local IDs (entities positive, terminal
    attribute negative) — the inverse of ``_resolve_entity_id_path_to_named_path``.

    Each segment is ``"{DataModelId}:{~}{UniqueName}"``. The ``{DataModelId}:`` prefix is stripped
    and ignored (portability); the ``UniqueName`` is resolved within the anchor data model (and its
    base model, for Org/Partner LIF) via ``get_unique_entity`` / ``get_unique_attribute``.

    Raises ``UnmatchedPathError`` if the path is empty, a segment is malformed, an attribute
    segment is not last, or a ``UniqueName`` does not resolve in this database.
    """
    if not named_path:
        raise UnmatchedPathError("path is empty")

    segments = named_path.split(",")
    resolved_ids: List[int] = []
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        # Strip and ignore the originating "{DataModelId}:" prefix — it is not a local ID.
        _prefix, separator, remainder = segment.partition(":")
        if not separator or not remainder:
            raise UnmatchedPathError(f"malformed path segment '{segment}' (expected '<id>:<UniqueName>')")

        is_attribute = remainder.startswith("~")
        unique_name = remainder[1:] if is_attribute else remainder
        if not unique_name:
            raise UnmatchedPathError(f"malformed path segment '{segment}' (missing UniqueName)")
        if is_attribute and not is_last:
            raise UnmatchedPathError(f"attribute segment '{segment}' must be the last segment in the path")

        if is_attribute:
            record = await get_unique_attribute(
                session=session,
                unique_name=unique_name,
                data_model_id=anchor_data_model.Id,
                base_data_model_id=anchor_data_model.BaseDataModelId,
                data_model_type=anchor_data_model.Type,
            )
        else:
            record = await get_unique_entity(
                session=session,
                unique_name=unique_name,
                data_model_id=anchor_data_model.Id,
                base_data_model_id=anchor_data_model.BaseDataModelId,
                data_model_type=anchor_data_model.Type,
            )

        if not record:
            kind = "attribute" if is_attribute else "entity"
            raise UnmatchedPathError(
                f"no {kind} named '{unique_name}' found in data model {anchor_data_model.Name} ({anchor_data_model.Id}) (or its base model)"
            )

        resolved_ids.append(-record.Id if is_attribute else record.Id)

    return resolved_ids


async def _resolve_and_validate_import_path(
    session: AsyncSession, named_path: str | None, anchor_data_model: DataModel
) -> tuple[dict | None, str]:
    """Resolve + validate one import path.

    Returns ``(resolved, "")`` on success, where ``resolved`` carries the numeric ``id_path`` plus
    the terminal ``attribute_id`` and owning ``entity_id`` (``TransformationAttributes.AttributeId``
    is NOT NULL, so it must be repopulated on import). Returns ``(None, reason)`` for any non-match:
    an unresolvable name, a path not ending in an attribute, or a name-resolvable path that is not a
    valid chain in the anchor data model (per decision, folded into the same non-match list).
    """
    if not named_path:
        return None, "missing entity path"
    try:
        ids = await resolve_named_path(session=session, named_path=named_path, anchor_data_model=anchor_data_model)
    except UnmatchedPathError as error:
        return None, error.reason

    if ids[-1] >= 0:
        return None, "portable path must end in an attribute"

    id_path = ",".join(str(node_id) for node_id in ids)
    try:
        # Reuse the #843 chain validator against the freshly resolved LOCAL numeric path.
        await check_transformation_attribute(session=session, anchor_data_model=anchor_data_model, id_path=id_path)
    except HTTPException as error:
        return None, f"resolved by name but is not a valid chain in this data model: {error.detail}"

    return {"id_path": id_path, "attribute_id": abs(ids[-1]), "entity_id": ids[-2] if len(ids) >= 2 else None}, ""


def _build_import_attribute(
    file_attribute: ImportTransformationAttributeDTO, attribute_type: AttributeType, resolved: dict
) -> CreateTransformationAttributeDTO:
    return CreateTransformationAttributeDTO(
        AttributeType=attribute_type,
        AttributeId=resolved["attribute_id"],
        EntityId=resolved["entity_id"],
        EntityIdPath=resolved["id_path"],
        Notes=file_attribute.Notes,
        CreationDate=file_attribute.CreationDate,
        ActivationDate=file_attribute.ActivationDate,
        DeprecationDate=file_attribute.DeprecationDate,
        Contributor=file_attribute.Contributor,
        ContributorOrganization=file_attribute.ContributorOrganization,
    )


async def _next_major_group_version(session: AsyncSession, source_data_model_id: int, target_data_model_id: int) -> str:
    """Return the next major group version ("{max_major + 1}.0") across non-deleted groups for this
    (source, target) pair. Non-numeric leading majors are ignored."""
    # `IS NOT TRUE` (not `== False`) so a Deleted = NULL row still counts as occupying its version,
    # matching the partial unique index ux_transformationsgroup_model_id_version_active — otherwise the
    # computed next-major could collide with a NULL-deleted group and trip an IntegrityError.
    query = select(TransformationGroup.GroupVersion).where(
        TransformationGroup.SourceDataModelId == source_data_model_id,
        TransformationGroup.TargetDataModelId == target_data_model_id,
        TransformationGroup.Deleted.isnot(True),
    )
    result = await session.execute(query)
    max_major = 0
    for version in result.scalars().all():
        if not version:
            continue
        try:
            max_major = max(max_major, int(str(version).split(".")[0]))
        except ValueError:
            continue
    return f"{max_major + 1}.0"


async def import_transformation_group(
    session: AsyncSession,
    transformation_group_id: int,
    data: ImportTransformationGroupRequestDTO,
    version: str | None,
    allow_missing_paths: bool,
) -> ImportTransformationGroupResultDTO:
    """Import a portable transformation-group file (#772).

    Runs as a single transaction (see ``create_transformation``/``create_transformation_group``'s
    ``commit=False``): every transformation is validated and staged as we go, then a single commit
    (or a rollback, when there are non-matches and ``allow_missing_paths`` is False) is issued at the
    end. This gives atomicity ("make no changes on failure") without a separate check/apply phase
    that could straddle commits.

    Version semantics: blank -> clone into the next major version; a version that already exists for
    this (source, target) -> edit (Layer 2, not yet implemented); a new, specified version -> clone
    into that version.
    """
    # The ONLY database ID matched from the request; source/target models are derived from it.
    reference_group = await get_transformation_group_by_id(session=session, id=transformation_group_id)
    source_data_model = await check_datamodel_by_id(session=session, id=reference_group.SourceDataModelId)
    target_data_model = await check_datamodel_by_id(session=session, id=reference_group.TargetDataModelId)

    normalized_version = (version or "").strip()
    if normalized_version:
        existing_group = await find_transformation_group_by_triplet(
            session=session,
            source_id=reference_group.SourceDataModelId,
            target_id=reference_group.TargetDataModelId,
            group_version=normalized_version,
            include_deleted=False,
        )
        if existing_group:
            logger.warning(
                "Import transformation group failed - there is already a transformation group with the same source, target, and version of (%s, %s, %s)",
                source_data_model.Id,
                target_data_model.Id,
                normalized_version,
            )
            raise HTTPException(
                status_code=501,
                detail=(
                    f"A transformation group already exists at version '{normalized_version}'. Editing an "
                    "existing version via import is not yet supported; omit the version to clone into the "
                    "next major version, or specify a new version."
                ),
            )
        resolved_version = normalized_version
    else:
        resolved_version = await _next_major_group_version(
            session, reference_group.SourceDataModelId, reference_group.TargetDataModelId
        )

    # Clone the group (metadata only, per the ticket). File-supplied metadata wins, falling back to
    # the referenced group. Source/target/version are authoritative (derived / from the parameter).
    new_group = await create_transformation_group(
        session=session,
        data=CreateTransformationGroupDTO(
            SourceDataModelId=reference_group.SourceDataModelId,
            TargetDataModelId=reference_group.TargetDataModelId,
            GroupVersion=resolved_version,
            Name=data.Name or reference_group.Name,
            Description=data.Description if data.Description is not None else reference_group.Description,
            Notes=data.Notes if data.Notes is not None else reference_group.Notes,
            CreationDate=data.CreationDate,
            ActivationDate=data.ActivationDate,
            DeprecationDate=data.DeprecationDate,
            Contributor=data.Contributor if data.Contributor is not None else reference_group.Contributor,
            ContributorOrganization=(
                data.ContributorOrganization
                if data.ContributorOrganization is not None
                else reference_group.ContributorOrganization
            ),
        ),
        commit=False,
    )

    non_matches: List[TransformationImportNonMatchDTO] = []
    imported_count = 0
    skipped_count = 0

    for transformation in data.Transformations or []:
        # Out of scope for portable import: silently-ignored on export, warned-and-skipped here.
        if transformation.ExpressionLanguage != ExpressionLanguageType.JSONata:
            logger.warning(
                f"Import: skipping transformation '{transformation.Name}' — non-JSONata expression language "
                f"'{transformation.ExpressionLanguage}' is out of scope for portable import."
            )
            continue
        if not transformation.Expression:
            logger.warning(f"Import: skipping transformation '{transformation.Name}' — it has no expression.")
            continue

        transformation_non_matches: List[TransformationImportNonMatchDTO] = []
        source_attributes: List[CreateTransformationAttributeDTO] = []

        file_source_attributes = transformation.SourceAttributes or []
        if not file_source_attributes:
            transformation_non_matches.append(
                TransformationImportNonMatchDTO(
                    TransformationName=transformation.Name,
                    AttributeType=AttributeType.Source,
                    NamedPath=None,
                    Reason="transformation has no source attributes",
                )
            )
        for source_attribute in file_source_attributes:
            resolved, reason = await _resolve_and_validate_import_path(
                session, source_attribute.EntityIdPath, source_data_model
            )
            if resolved is None:
                transformation_non_matches.append(
                    TransformationImportNonMatchDTO(
                        TransformationName=transformation.Name,
                        AttributeType=AttributeType.Source,
                        NamedPath=source_attribute.EntityIdPath,
                        Reason=reason,
                    )
                )
            else:
                source_attributes.append(_build_import_attribute(source_attribute, AttributeType.Source, resolved))

        target_attribute: CreateTransformationAttributeDTO | None = None
        if transformation.TargetAttribute is None:
            transformation_non_matches.append(
                TransformationImportNonMatchDTO(
                    TransformationName=transformation.Name,
                    AttributeType=AttributeType.Target,
                    NamedPath=None,
                    Reason="transformation has no target attribute",
                )
            )
        else:
            resolved, reason = await _resolve_and_validate_import_path(
                session, transformation.TargetAttribute.EntityIdPath, target_data_model
            )
            if resolved is None:
                transformation_non_matches.append(
                    TransformationImportNonMatchDTO(
                        TransformationName=transformation.Name,
                        AttributeType=AttributeType.Target,
                        NamedPath=transformation.TargetAttribute.EntityIdPath,
                        Reason=reason,
                    )
                )
            else:
                target_attribute = _build_import_attribute(
                    transformation.TargetAttribute, AttributeType.Target, resolved
                )

        # Skip the WHOLE transformation if any of its paths did not resolve/validate.
        if transformation_non_matches:
            non_matches.extend(transformation_non_matches)
            skipped_count += 1
            continue

        # An empty non-match list guarantees the target resolved; this guard is unreachable in
        # practice but lets the type checker narrow target_attribute to non-None without an assert.
        if target_attribute is None:
            continue

        await create_transformation(
            session=session,
            data=CreateTransformationDTO(
                TransformationGroupId=new_group.Id,
                Name=transformation.Name,
                Expression=transformation.Expression,
                ExpressionLanguage=transformation.ExpressionLanguage,
                Notes=transformation.Notes,
                Alignment=transformation.Alignment,
                CreationDate=transformation.CreationDate,
                ActivationDate=transformation.ActivationDate,
                DeprecationDate=transformation.DeprecationDate,
                Contributor=transformation.Contributor,
                ContributorOrganization=transformation.ContributorOrganization,
                SourceAttributes=source_attributes,
                TargetAttribute=target_attribute,
            ),
            commit=False,
        )
        imported_count += 1

    if non_matches and not allow_missing_paths:
        # Fail the call and do NOT make any changes.
        await session.rollback()
        return ImportTransformationGroupResultDTO(
            Success=False,
            TransformationGroupId=None,
            ImportedTransformationCount=0,
            SkippedTransformationCount=skipped_count,
            MissingPaths=non_matches,
        )

    if imported_count == 0:
        # Importing a transformation group with no transformations is not allowed (mirrors the export
        # side, which refuses to emit an empty group). Reached when the file has no JSONata
        # transformations or when every transformation was skipped for missing paths under
        # allowMissingPaths=true.
        await session.rollback()
        raise HTTPException(
            status_code=400,
            detail=(
                "No transformations were imported, so no transformation group was created. A "
                "transformation group must contain at least one JSONata transformation whose "
                "attribute paths all resolve in this database."
            ),
        )

    await session.commit()
    return ImportTransformationGroupResultDTO(
        Success=True,
        TransformationGroupId=new_group.Id,
        ImportedTransformationCount=imported_count,
        SkippedTransformationCount=skipped_count,
        MissingPaths=non_matches,
    )
