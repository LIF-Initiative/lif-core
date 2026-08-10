from typing import List, Optional
from pydantic import BaseModel


from datetime import datetime

from lif.datatypes.mdr_sql_model import DataModelType, StateType
from lif.mdr_dto.attribute_dto import AttributeDTO
from lif.mdr_dto.entity_dto import ChildEntityDTO, EntityDTO

# from service.app.models.DTO.import_export_dto import  ValueSetExportDTO
from lif.mdr_dto.value_set_values_dto import ValueSetValueDTO
from lif.mdr_dto.valueset_dto import ValueSetDTO


class DataModelDTO(BaseModel):
    Id: Optional[int]
    Name: str
    Description: Optional[str]
    UseConsiderations: Optional[str]
    Type: DataModelType  # Assuming Type is an enum, it can be replaced by the specific enum type if required
    BaseDataModelId: Optional[int]
    Notes: Optional[str]
    DataModelVersion: Optional[str]
    CreationDate: Optional[datetime]
    ActivationDate: Optional[datetime]
    DeprecationDate: Optional[datetime]
    Contributor: Optional[str]
    ContributorOrganization: Optional[str]
    State: Optional[StateType]
    Tags: Optional[str] = None
    Deleted: Optional[bool] = False

    class Config:
        orm_mode = True  # This allows Pydantic to work with SQLModel/ORM objects
        from_attributes = True  # This enables the use of `from_orm`


class CreateDataModelDTO(BaseModel):
    Name: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Type: DataModelType  # Assuming Type is an enum, it can be replaced by the specific enum type if required
    BaseDataModelId: Optional[int] = None
    Notes: Optional[str] = None
    DataModelVersion: str
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    State: Optional[StateType] = StateType.Draft
    Deleted: Optional[bool] = False
    Tags: Optional[str] = None


class UpdateDataModelDTO(BaseModel):
    Name: Optional[str] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Type: Optional[DataModelType] = (
        None  # Assuming Type is an enum, it can be replaced by the specific enum type if required
    )
    BaseDataModelId: Optional[int] = None
    Notes: Optional[str] = None
    DataModelVersion: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    State: Optional[StateType] = None
    Tags: Optional[str] = None


# class DataModelEntityDTO(BaseModel):
#     DataModel: DataModelDTO
#     Entities: List[EntityDTO]


class ValueSetValuesDTO(BaseModel):
    ValueSet: ValueSetDTO
    Values: List[ValueSetValueDTO]


class EntityAttributeExportDTO(BaseModel):
    Entity: EntityDTO
    Attributes: List[AttributeDTO]
    ParentEntities: Optional[List[EntityDTO]] = None
    ChildEntities: Optional[List[ChildEntityDTO]] = None


class DataModelWithDetailsDTO(BaseModel):
    DataModel: DataModelDTO
    Entities: List[EntityAttributeExportDTO]
    ValueSets: List[ValueSetValuesDTO]
    # Transformations: TransformationListDTO
    # DataModelConstraints: List[DataModelConstraintsDTO]
