from typing import Dict, List, Optional
from fastapi import HTTPException
from lif.mdr_sql_model.core import (
    Attribute,
    DataModel,
    Entity,
    Transformation,
    TransformationGroup,
    ValueSet,
    ValueSetValue,
)
from lif.mdr_dto.attribute_dto import AttributeDTO
from lif.mdr_dto.datamodel_dto import DataModelDTO
from lif.mdr_dto.entity_dto import EntityDTO
from lif.mdr_dto.transformation_dto import TransformationDTO
from lif.mdr_dto.transformation_group_dto import TransformationGroupDTO
from lif.mdr_dto.value_set_values_dto import ValueSetValueDTO
from lif.mdr_dto.valueset_dto import ValueSetDTO
from lif.mdr_services.transformation_service import get_transformation_by_id, get_transformation_group_by_id
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy import or_, cast, String, and_


async def search_data_model(
    session: AsyncSession,
    search_key: str,
    data_model_id: Optional[int] = None,
    contributor_organization: Optional[str] = None,
    only_extension: Optional[bool] = False,
    only_base: Optional[bool] = False,
) -> Dict[str, List]:
    dm_list_for_search: list[int] = []
    extended_dms = None
    base_dms = None
    if only_extension:
        extension_dm_query = select(DataModel.Id).where(
            DataModel.BaseDataModelId.isnot(None), DataModel.Deleted == False
        )
        result = await session.execute(extension_dm_query)
        extended_dms = result.scalars().all()
        # if data_model_id:
        #     if data_model_id not in extended_dms:
        #         raise HTTPException(status_code=400, detail=f"You have selected Only Extension search and provided Data model '{data_model_id}' is not extension")
        dm_list_for_search = extended_dms

    if only_base:
        base_dm_query = select(DataModel.Id).where(DataModel.BaseDataModelId.is_(None), DataModel.Deleted == False)
        result = await session.execute(base_dm_query)
        base_dms = result.scalars().all()
        dm_list_for_search = base_dms

    if only_base and only_extension:
        dm_list_for_search = extended_dms + base_dms

    if data_model_id and len(dm_list_for_search) > 0:
        if data_model_id not in dm_list_for_search:
            raise HTTPException(
                status_code=400,
                detail=f"Provided Data model '{data_model_id}' is not in the list of data model for search, which is created based on the only_extension and only_base ",
            )
        # Giving more priority to data model id if it is provided
        dm_list_for_search = [data_model_id]

    if data_model_id and len(dm_list_for_search) == 0:
        dm_list_for_search.append(data_model_id)

    # Define a wildcard search pattern for case-insensitive search
    search_pattern = f"%{search_key}%"

    # Query for Entities
    entity_query = select(Entity).where(
        or_(
            Entity.Name.ilike(search_pattern),
            Entity.UniqueName.ilike(search_pattern),
            Entity.Tags.ilike(search_pattern),
            Entity.Contributor.ilike(search_pattern),
        ),
        Entity.Deleted == False,
        (Entity.ContributorOrganization.ilike(contributor_organization) if contributor_organization else True),
        (Entity.DataModelId.in_(dm_list_for_search) if len(dm_list_for_search) > 0 else True),
    )
    entity_results = await session.execute(entity_query)
    entities = entity_results.scalars().all()
    entities_dtos = [EntityDTO.from_orm(entity) for entity in entities]

    # Query for Attributes
    attribute_query = select(Attribute).where(
        or_(
            Attribute.Name.ilike(search_pattern),
            Attribute.UniqueName.ilike(search_pattern),
            Attribute.Contributor.ilike(search_pattern),
            Attribute.Tags.ilike(search_pattern),
        ),
        Attribute.Deleted == False,
        (Attribute.ContributorOrganization.ilike(contributor_organization) if contributor_organization else True),
        (Attribute.DataModelId.in_(dm_list_for_search) if len(dm_list_for_search) > 0 else True),
    )
    attribute_results = await session.execute(attribute_query)
    attributes = attribute_results.scalars().all()
    attribute_dtos = [AttributeDTO.from_orm(attribute) for attribute in attributes]

    # Query for Data Models
    data_model_query = select(DataModel).where(
        or_(
            DataModel.Name.ilike(search_pattern),
            DataModel.Contributor.ilike(search_pattern),
            DataModel.ContributorOrganization.ilike(search_pattern),
            DataModel.Tags.ilike(search_pattern),
            cast(DataModel.State, String).ilike(search_pattern),
        ),
        DataModel.Deleted == False,
        (DataModel.ContributorOrganization.ilike(contributor_organization) if contributor_organization else True),
        (DataModel.Id.in_(dm_list_for_search) if len(dm_list_for_search) > 0 else True),
    )
    data_model_results = await session.execute(data_model_query)
    data_models = data_model_results.scalars().all()
    datamodel_dtos = [DataModelDTO.from_orm(datamodel) for datamodel in data_models]

    # Query for Value Sets
    value_set_query = select(ValueSet).where(
        or_(
            ValueSet.Name.ilike(search_pattern),
            ValueSet.Contributor.ilike(search_pattern),
            ValueSet.Tags.ilike(search_pattern),
        ),
        ValueSet.Deleted == False,
        (ValueSet.ContributorOrganization.ilike(contributor_organization) if contributor_organization else True),
        (ValueSet.DataModelId.in_(dm_list_for_search) if len(dm_list_for_search) > 0 else True),
    )
    value_set_results = await session.execute(value_set_query)
    value_sets = value_set_results.scalars().all()
    value_set_dtos = [ValueSetDTO.from_orm(value_set) for value_set in value_sets]

    # Query for Value Set Values
    value_set_values_query = select(ValueSetValue).where(
        and_(
            or_(ValueSetValue.Value.ilike(search_pattern), ValueSetValue.ValueName.ilike(search_pattern)),
            ValueSetValue.Deleted == False,
            (
                ValueSetValue.ContributorOrganization.ilike(contributor_organization)
                if contributor_organization
                else True
            ),
            (
                ValueSetValue.DataModelId.in_(dm_list_for_search) if len(dm_list_for_search) > 0 else True
            ),  # Filter by ValueSet.DataModelId
        )
    )
    value_set_values_results = await session.execute(value_set_values_query)
    value_set_values = value_set_values_results.scalars().all()
    valueset_value_dtos = [ValueSetValueDTO.from_orm(value) for value in value_set_values]

    # Query to get transformation group
    transformation_group_query = select(TransformationGroup.Id).where(
        or_(
            TransformationGroup.Name.ilike(search_pattern),
            TransformationGroup.Notes.ilike(search_pattern),
            TransformationGroup.Contributor.ilike(search_pattern),
            TransformationGroup.Tags.ilike(search_pattern),
        ),
        TransformationGroup.Deleted == False,
        (
            TransformationGroup.ContributorOrganization.ilike(contributor_organization)
            if contributor_organization
            else True
        ),
    )
    if len(dm_list_for_search) > 0:
        transformation_group_query = transformation_group_query.where(
            or_(
                TransformationGroup.SourceDataModelId.in_(dm_list_for_search),
                TransformationGroup.TargetDataModelId.in_(dm_list_for_search),
            )
        )
    transformation_group_results = await session.execute(transformation_group_query)
    transformation_group_ids = transformation_group_results.scalars().all()
    transformation_group_dtos: List[TransformationGroupDTO] = []
    for id in transformation_group_ids:
        transformation_group = await get_transformation_group_by_id(session=session, id=id)
        transformation_group_dto = TransformationGroupDTO.from_orm(transformation_group)
        transformation_group_dtos.append(transformation_group_dto)

    # Query for Transformations
    transformation_query = (
        select(Transformation.Id)
        .join(TransformationGroup, Transformation.TransformationGroupId == TransformationGroup.Id)
        .where(
            or_(
                Transformation.Name.ilike(search_pattern),
                Transformation.Notes.ilike(search_pattern),
                Transformation.Expression.ilike(search_pattern),
                Transformation.Contributor.ilike(search_pattern),
            ),
            TransformationGroup.Deleted == False,
            Transformation.Deleted == False,
            (
                Transformation.ContributorOrganization.ilike(contributor_organization)
                if contributor_organization
                else True
            ),
        )
    )
    if len(dm_list_for_search) > 0:
        transformation_query = transformation_query.where(
            or_(
                TransformationGroup.SourceDataModelId.in_(dm_list_for_search),
                TransformationGroup.TargetDataModelId.in_(dm_list_for_search),
            )
        )
    transformation_results = await session.execute(transformation_query)
    transformation_ids = transformation_results.scalars().all()
    transformation_dtos: List[TransformationDTO] = []
    for id in transformation_ids:
        transformation_dto = await get_transformation_by_id(session=session, transformation_id=id)
        transformation_dtos.append(transformation_dto)

    # # Query for Transformation Attributes
    # transformation_attr_query = select(TransformationAttribute).where(
    #     or_(
    #         TransformationAttribute.Notes.ilike(search_pattern),
    #         TransformationAttribute.Contributor.ilike(search_pattern),
    #         TransformationAttribute.ContributorOrganization.ilike(search_pattern),
    #     )
    # )
    # transformation_attr_results = await session.execute(transformation_attr_query)
    # transformation_attributes = transformation_attr_results.scalars().all()

    # Combine results into a single response
    return {
        "data_models": datamodel_dtos,
        "entities": entities_dtos,
        "attributes": attribute_dtos,
        "value_sets": value_set_dtos,
        "value_set_values": valueset_value_dtos,
        "transformation_groups": transformation_group_dtos,
        "transformations": transformation_dtos,
    }
