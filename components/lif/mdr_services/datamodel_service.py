from typing import Any, List, Optional

from fastapi import HTTPException
from lif.datatypes.mdr_sql_model import (
    AccessType,
    DataModel,
    DataModelType,
    Entity,
    ExtInclusionsFromBaseDM,
    StateType,
    ValueSet,
    ValueSetValue,
)
from lif.mdr_dto.datamodel_dto import (
    CreateDataModelDTO,
    DataModelDTO,
    DataModelWithDetailsDTO,
    EntityAttributeExportDTO,
    UpdateDataModelDTO,
    ValueSetValuesDTO,
)
from lif.mdr_services.attribute_service import get_list_of_attributes_for_entity
from lif.mdr_services.datamodel_constraints_service import get_data_model_constraints_by_data_model_id
from lif.mdr_services.entity_service import (
    get_filtered_entity_children,
    get_filtered_entity_parents,
    get_list_of_entities_for_data_model,
    soft_delete_entity,
)
from lif.mdr_services.inclusions_service import soft_delete_data_model_ext_inclusions
from lif.mdr_services.schema_upload_service import update_data_model_from_openapi_schema
from lif.mdr_services.transformation_service import get_transformations_by_data_model_id
from lif.mdr_services.value_set_values_service import get_list_of_values_for_value_set, soft_delete_value_set_value
from lif.mdr_services.valueset_service import get_value_sets_by_data_model_id_and_attributes, soft_delete_value_set
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

logger = get_logger(__name__)


async def get_all_datamodels(session: AsyncSession):
    result = await session.execute(select(DataModel))
    return result.scalars().all()


async def get_paginated_datamodels(
    session: AsyncSession,
    offset: int = 0,
    limit: int = 0,
    pagination: bool = True,
    level_of_access: AccessType = None,
    state: StateType = None,
    include_extension: bool = True,
):
    # Query to count total records
    total_query = select(func.count(DataModel.Id)).where(
        DataModel.Deleted == False, (DataModel.State == state if state else True)
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar()

    # Query to fetch paginated results
    if pagination:
        query = (
            select(DataModel)
            .where(DataModel.Deleted == False, (DataModel.State == state if state else True))
            .order_by(DataModel.Id)
            .offset(offset)
            .limit(limit)
        )
    else:
        query = (
            select(DataModel)
            .where(DataModel.Deleted == False, (DataModel.State == state if state else True))
            .order_by(DataModel.Id)
        )
    result = await session.execute(query)
    datamodels = result.scalars().all()

    # Convert the list of DataModel objects to DataModelDTO objects
    datamodel_dtos = [DataModelDTO.from_orm(datamodel) for datamodel in datamodels]

    return total_count, datamodel_dtos


async def get_datamodel_by_id(session: AsyncSession, id: int):
    datamodel = await session.get(DataModel, id)
    if not datamodel:
        raise HTTPException(status_code=404, detail="DataModel not found")
    if datamodel.Deleted:
        raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
    # return DataModelDTO.from_orm(datamodel)

    return datamodel


async def get_datamodel_with_details_by_id(
    session: AsyncSession, id: int, partner_only: bool = False, org_ext_only: bool = False, public_only: bool = False
):
    datamodel = await session.get(DataModel, id)
    if not datamodel:
        raise HTTPException(status_code=404, detail="DataModel not found")
    if datamodel.Deleted:
        raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
    data_model_dto = DataModelDTO.from_orm(datamodel)
    this_org = data_model_dto.ContributorOrganization

    # Get entities and attributes for those attributes:
    entity_attribute_list: List[EntityAttributeExportDTO] = []
    total_entities, entities = await get_list_of_entities_for_data_model(
        session=session,
        data_model_id=id,
        pagination=False,
        partner_only=partner_only,
        org_ext_only=org_ext_only,
        this_organization=this_org,
        public_only=public_only,
    )
    for entity in entities:
        # attributes
        total_attributes, attributes = await get_list_of_attributes_for_entity(
            session=session,
            entity_id=entity.Id,
            data_model_id=id,
            pagination=False,
            data_model_type=datamodel.Type,
            partner_only=partner_only,
            this_organization=this_org,
            public_only=public_only,
        )
        # parents
        parent_entities = await get_filtered_entity_parents(
            session=session,
            entity_id=entity.Id,
            partner_only=partner_only,
            org_ext_only=org_ext_only,
            public_only=public_only,
            this_organization=this_org,
            data_model_id=id,
            data_model_type=datamodel.Type,
        )
        # children
        child_entities = await get_filtered_entity_children(
            session=session,
            entity_id=entity.Id,
            partner_only=partner_only,
            org_ext_only=org_ext_only,
            public_only=public_only,
            this_organization=this_org,
            data_model_id=id,
            data_model_type=datamodel.Type,
        )
        entity_attribute_dto = EntityAttributeExportDTO(
            Entity=entity, Attributes=attributes, ParentEntities=parent_entities, ChildEntities=child_entities
        )
        entity_attribute_list.append(entity_attribute_dto)

    # Getting value set and its values
    value_set_list = await get_value_sets_by_data_model_id_and_attributes(
        session=session, data_model_id=id, entity_attribute_export_list=entity_attribute_list
    )
    list_value_set_export_dtos: list[ValueSetValuesDTO] = []
    for value_set in value_set_list:
        total_values, values = await get_list_of_values_for_value_set(
            session=session, valueset_id=value_set.Id, pagination=False
        )
        value_set_export_dto = ValueSetValuesDTO(ValueSet=value_set, Values=values)
        list_value_set_export_dtos.append(value_set_export_dto)

    # Getting all the transformation
    transformations = await get_transformations_by_data_model_id(session=session, data_model_id=id)

    total_constraints, data_model_constraints = await get_data_model_constraints_by_data_model_id(
        session=session, data_model_id=id, pagination=False
    )

    return DataModelWithDetailsDTO(
        DataModel=data_model_dto,
        Entities=entity_attribute_list,
        ValueSets=list_value_set_export_dtos,
        Transformations=transformations,
        DataModelConstraints=data_model_constraints,
    )


async def get_datamodel_by_entity_id(session: AsyncSession, entity_id: int):
    entity_query = select(Entity).where(Entity.Id == entity_id, Entity.Deleted == False)
    result = await session.execute(entity_query)
    data_model = result.scalars().first()
    return await get_datamodel_by_id(session=session, id=data_model.DataModelId)


async def create_datamodel(session: AsyncSession, data: CreateDataModelDTO):
    # Check if a data model with the same name exists
    if (
        await check_unique_data_model_exists(
            session, data.Name, data.DataModelVersion, data.Type, data.ContributorOrganization
        )
        != None
    ):
        raise HTTPException(status_code=400, detail=f"DataModel with name '{data.Name}' already exists")
    if (data.Type in (DataModelType.OrgLIF, DataModelType.PartnerLIF)) and not data.BaseDataModelId:
        raise HTTPException(status_code=400, detail="DataModel OrgLIF or PartnerLIF requires base data model id.")
    if (data.Type in (DataModelType.BaseLIF, DataModelType.SourceSchema)) and data.BaseDataModelId:
        logger.info("This is BaseLIF or SourceSchema type model so this does not require Base data model id")
        data.BaseDataModelId = None
    datamodel = DataModel(**data.dict())
    session.add(datamodel)
    await session.commit()
    await session.refresh(datamodel)
    return DataModelDTO.from_orm(datamodel)


async def update_datamodel(session: AsyncSession, id: int, metadata: UpdateDataModelDTO, data: Optional[Any] = None):
    datamodel = await session.get(DataModel, id)
    if not datamodel:
        raise HTTPException(status_code=404, detail="Data Model not found")
    if datamodel.Deleted:
        raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
    # if Name, Version, or ContributorOrganization are different between the persistent
    # data model and requested changes, throw an exception
    if (
        datamodel.Name != metadata.Name
        or datamodel.DataModelVersion != metadata.DataModelVersion
        or datamodel.ContributorOrganization != metadata.ContributorOrganization
    ) and await check_unique_data_model_exists(
        session, metadata.Name, metadata.DataModelVersion, metadata.Type, metadata.ContributorOrganization
    ) != None:
        raise HTTPException(
            status_code=400,
            detail=f"DataModel with name '{metadata.Name}', version '{metadata.DataModelVersion}', and contributor organization '{metadata.ContributorOrganization}' already exists",
        )

    # Update the metadata of the data model

    for key, value in metadata.dict(exclude_unset=True).items():
        setattr(datamodel, key, value)

    session.add(datamodel)
    await session.flush()

    logger.info(f"Updating Data Model ID {datamodel.Id}. New schema data: {str(data)}")
    # Update the schema if provided
    if data:
        await update_data_model_from_openapi_schema(session, datamodel, data)

    await session.commit()
    await session.refresh(datamodel)
    return DataModelDTO.from_orm(datamodel)


async def delete_datamodel(session: AsyncSession, id: int):
    datamodel = await session.get(DataModel, id)
    if not datamodel:
        raise HTTPException(status_code=404, detail="DataModel not found")
    if datamodel.Deleted:
        raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
    if datamodel.Type == DataModelType.BaseLIF:
        raise HTTPException(status_code=400, detail="BaseLIF cannot be deleted")

    await session.delete(datamodel)
    await session.commit()
    return {"ok": True}


async def soft_delete_data_model(session: AsyncSession, data_model_id: int) -> dict:
    data_model = await session.get(DataModel, data_model_id)
    if not data_model or data_model.Deleted:
        raise HTTPException(status_code=404, detail=f"DataModel with ID {data_model_id} not found or already deleted")
    if data_model.Type == DataModelType.BaseLIF:
        raise HTTPException(status_code=400, detail="BaseLIF cannot be deleted")

    # Delete usage of this data model as indicated in ExtInclusionsFromBaseDM
    ext_inclusions_query = select(ExtInclusionsFromBaseDM).where(
        ExtInclusionsFromBaseDM.ExtDataModelId == data_model_id, ExtInclusionsFromBaseDM.Deleted == False
    )
    result = await session.execute(ext_inclusions_query)
    ext_inclusions = result.scalars().all()
    for ext_inclusion in ext_inclusions:
        await soft_delete_data_model_ext_inclusions(session=session, data_model_id=ext_inclusion.Id)

    # Delete associations in the EntityAttributeAssociation table
    entity_query = select(Entity).where(Entity.DataModelId == data_model_id, Entity.Deleted == False)
    result = await session.execute(entity_query)
    entities = result.scalars().all()
    for entity in entities:
        await soft_delete_entity(session=session, id=entity.Id)

    value_set_query = select(ValueSet).where(ValueSet.DataModelId == data_model_id, ValueSet.Deleted == False)
    result = await session.execute(value_set_query)
    value_sets = result.scalars().all()
    for value_set in value_sets:
        await soft_delete_value_set(session=session, id=value_set.Id)

    value_set_value_query = select(ValueSetValue).where(
        ValueSetValue.DataModelId == data_model_id, ValueSetValue.Deleted == False
    )
    result = await session.execute(value_set_value_query)
    value_set_values = result.scalars().all()
    for values in value_set_values:
        await soft_delete_value_set_value(session=session, id=values.Id)

    data_model.Deleted = True
    session.add(data_model)
    await session.commit()

    return {"message": f"DataModel with ID {data_model_id} marked as deleted"}


async def is_datamodel_orglif(session: AsyncSession, id: int):
    datamodel = await session.get(DataModel, id)
    if not datamodel:
        raise HTTPException(status_code=404, detail="DataModel not found")
    if datamodel.Deleted:
        raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
    if datamodel.Type == DataModelType.OrgLIF:
        return True
    return False


async def get_list_of_orglif_model(
    session: AsyncSession, contributor_organization: Optional[str] = None, state: StateType = None
):
    data_model_query = select(DataModel).where(
        DataModel.Type == DataModelType.OrgLIF,
        DataModel.Deleted == False,
        (DataModel.State == state if state else True),
        (DataModel.ContributorOrganization == contributor_organization if contributor_organization else True),
    )
    result = await session.execute(data_model_query)
    data_models = result.scalars().all()
    # total_count = len(data_models)
    # Convert the list of DataModel objects to DataModelDTO objects
    datamodel_dtos = [DataModelDTO.from_orm(datamodel) for datamodel in data_models]

    return datamodel_dtos


async def get_extensions_for_data_model(
    session: AsyncSession,
    data_model_id: int,
    contributor: str = None,
    contributorOrganization: str = None,
    state: StateType = None,
):
    # Start with the base query
    query = select(DataModel).where(
        DataModel.BaseDataModelId == data_model_id,
        DataModel.Type == "OrgLIF",
        DataModel.Deleted == False,
        (DataModel.State == state if state else True),
    )

    if contributor and contributorOrganization:
        query = query.where(
            or_(
                DataModel.Contributor.ilike(f"%{contributor}%"),
                DataModel.ContributorOrganization.ilike(f"%{contributorOrganization}%"),
            )
        )
    # Add the Contributor ILIKE filter if provided
    elif contributor:
        query = query.where(DataModel.Contributor.ilike(f"%{contributor}%"))

    # Add the ContributorOrganization ILIKE filter if provided
    elif contributorOrganization:
        query = query.where(DataModel.ContributorOrganization.ilike(f"%{contributorOrganization}%"))

    # Execute the query
    result = await session.execute(query)
    extensions = result.scalars().all()

    datamodel_dtos = [DataModelDTO.from_orm(datamodel) for datamodel in extensions]

    return datamodel_dtos


async def get_partner_extensions_for_data_model(
    session: AsyncSession,
    data_model_id: int,
    contributor: str = None,
    contributorOrganization: str = None,
    state: StateType = None,
):
    return await get_datamodel_with_details_by_id(
        session=session, id=data_model_id, partner_only=True, org_ext_only=False
    )


async def get_base_model_for_given_orglif(session: AsyncSession, extended_data_model_id: int):
    # Start with the base query
    query = select(DataModel).where(
        DataModel.Id == extended_data_model_id, DataModel.Type == "OrgLIF", DataModel.Deleted == False
    )
    # Execute the query
    result = await session.execute(query)
    extended_data_model = result.scalars().first()
    return await get_datamodel_by_id(session=session, id=extended_data_model.BaseDataModelId)


async def check_unique_data_model_exists(
    session: AsyncSession, name: str, version: str, dataModelType: str, contributorOrganization: str
) -> bool:
    # Query to check if a data model with the same name exists
    query = select(DataModel).where(
        DataModel.Name == name,
        DataModel.Type == dataModelType,
        DataModel.DataModelVersion == version,
        DataModel.ContributorOrganization == contributorOrganization,
        DataModel.Deleted == False,
    )
    result = await session.execute(query)
    existing_data_model = result.scalars().first()
    if existing_data_model:
        return existing_data_model
    else:
        return None


async def check_data_model_exists(session: AsyncSession, data: DataModelDTO) -> bool:
    # Query to check if a data model with the same name exists
    query = select(DataModel).where(
        DataModel.Name == data.Name,
        DataModel.Description == data.Description,
        DataModel.UseConsiderations == data.UseConsiderations,
        DataModel.Type == data.Type,
        DataModel.BaseDataModelId == data.BaseDataModelId,
        DataModel.DataModelVersion == data.DataModelVersion,
        DataModel.CreationDate == data.CreationDate,
        DataModel.ActivationDate == data.ActivationDate,
        DataModel.DeprecationDate == data.DeprecationDate,
        DataModel.Contributor == data.Contributor,
        DataModel.ContributorOrganization == data.ContributorOrganization,
        DataModel.State == data.State,
        DataModel.Tags == data.Tags,
        DataModel.Deleted == False,
    )
    result = await session.execute(query)
    existing_data_model = result.scalars().first()
    if existing_data_model:
        return existing_data_model
    else:
        return None


async def get_datamodels_by_ids(session: AsyncSession, ids: List[int]) -> List[DataModelDTO]:
    # Query to get the data models for the provided list of IDs
    query = select(DataModel).where(DataModel.Id.in_(ids), DataModel.Deleted == False)
    result = await session.execute(query)
    datamodels = result.scalars().all()

    # Convert the list of DataModel objects to DataModelDTO objects
    datamodel_dtos = [DataModelDTO.from_orm(datamodel) for datamodel in datamodels]

    return datamodel_dtos


async def get_datamodel_by_name(session: AsyncSession, name: str, version: str = None):
    query = select(DataModel).where(DataModel.Name == name)
    result = await session.execute(query)
    data_model = result.scalars().first()
    if not data_model:
        raise HTTPException(status_code=404, detail=f"Data Model with id {id}  not found")
    if data_model.Deleted:
        raise HTTPException(status_code=404, detail=f"Data Model with ID {id} is deleted")
    return DataModelDTO.from_orm(data_model)
