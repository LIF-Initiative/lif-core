from typing import List, Optional
from pydantic import BaseModel


from datetime import datetime

from lif.mdr_sql_model.core import DataModelType, DatamodelElementType
from lif.mdr_dto.attribute_dto import AttributeDTO
from lif.mdr_dto.datamodel_constraints_dto import DataModelConstraintsDTO
from lif.mdr_dto.datamodel_dto import CreateDataModelDTO, DataModelDTO
from lif.mdr_dto.entity_association_dto import EntityAssociationDTO
from lif.mdr_dto.entity_attribute_association_dto import EntityAttributeAssociationDTO
from lif.mdr_dto.entity_dto import EntityDTO
from lif.mdr_dto.transformation_dto import CreateTransformationWithTransformationGroupDTO, TransformationListDTO
from lif.mdr_dto.value_set_values_dto import ValueSetValueDTO
from lif.mdr_dto.valueset_dto import ValueSetDTO


class ValueSetExportDTO(BaseModel):
    ValueSet: ValueSetDTO
    Values: List[ValueSetValueDTO]


class EntityExportDTO(BaseModel):
    Entity: EntityDTO
    Attributes: List[AttributeDTO]


class SingleDataModelExportDTO(BaseModel):
    DataModel: DataModelDTO
    # Entities: List[EntityExportDTO]
    Entities: List[EntityDTO]
    Attributes: List[AttributeDTO]
    ValueSets: List[ValueSetExportDTO]
    Transformations: TransformationListDTO
    EntityAssociation: List[EntityAssociationDTO]
    EntityAttributeAssociation: List[EntityAttributeAssociationDTO]
    DataModelConstraints: List[DataModelConstraintsDTO]


class DataModelExportDTO(BaseModel):
    BaseDataModel: SingleDataModelExportDTO
    ExtendedDataModel: Optional[SingleDataModelExportDTO] = None


class ImportEntityDTO(BaseModel):
    Name: str
    DataModelId: Optional[int] = None
    UniqueName: Optional[str] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None
    Tags: Optional[str] = None


class ImportAttributeDTO(BaseModel):
    Name: str
    DataType: str
    DataModelId: Optional[int] = None
    EntityName: Optional[str] = None
    UniqueName: Optional[str] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    ValueSetName: Optional[str] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None


class ImportValueSetDTO(BaseModel):
    Name: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    DataModelId: Optional[int] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None


class ImportValueSetValueDTO(BaseModel):
    ValueSetId: Optional[int] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Value: str
    ValueName: Optional[str] = None
    OriginalValueId: Optional[int] = None
    Source: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None


class ImportValueSetWithValuesDTO(BaseModel):
    ValueSet: ImportValueSetDTO
    Values: List[ImportValueSetValueDTO]


class ImportEntityAttributeDTO(BaseModel):
    Entity: ImportEntityDTO
    Attributes: List[ImportAttributeDTO]


class ImportEntityAssociationDTO(BaseModel):
    ParentEntityName: str
    ParentDataModelName: Optional[str] = None
    ParentDataModelVersion: Optional[str] = None
    ChildEntityName: str
    ChildDataModelName: Optional[str] = None
    ChildDataModelVersion: Optional[str] = None
    Relationship: Optional[str] = None
    Placement: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None


class ImportEntityAttributeAssociationDTO(BaseModel):
    EntityName: str
    DataModelName: Optional[str] = None
    DataModelVersion: Optional[str] = None
    AttributeName: str
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None


class ImportTransformationGroupDTO(BaseModel):
    SourceDataModelName: Optional[str] = None
    SourceDataModelVersion: Optional[str] = None
    TargetDataModelName: Optional[str] = None
    TargetDataModelVersion: Optional[str] = None
    Name: Optional[str] = None
    GroupVersion: str
    Description: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Transformations: Optional[List[CreateTransformationWithTransformationGroupDTO]] = None
    Tags: Optional[str] = None


class ImportTransformationDTO(BaseModel):
    TransformationGroup: ImportTransformationGroupDTO
    Transformations: List[CreateTransformationWithTransformationGroupDTO]


# class DataModelImportDTO(BaseModel):
#     DataModel: CreateDataModelDTO
#     Entities: List[ImportEntityAttributeDTO]
#     ValueSets: List[ImportValueSetWithValuesDTO]
#     # Transformations: TransformationListDTO
#     EntityAssociation: List[AssociateEntityDTO]


class ImportDataModelConstraintsDTO(BaseModel):
    Name: Optional[str] = None
    Description: Optional[str] = None
    ForDataModelId: int
    ElementType: DatamodelElementType
    ElementName: str
    ConstraintType: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: str
    ContributorOrganization: str
    Deleted: Optional[bool] = False


class ImportDataModelDTO(BaseModel):
    DataModel: CreateDataModelDTO
    Entities: List[ImportEntityDTO]
    Attributes: List[ImportAttributeDTO]
    ValueSets: List[ImportValueSetWithValuesDTO]
    # Transformations: List[ImportTransformationDTO] -- Need to transformation after model is imported as we can have attributes with the same name in a model so it difficult to figure out the right attribute to map.
    EntityAssociation: List[ImportEntityAssociationDTO]
    DataModelConstraints: List[ImportDataModelConstraintsDTO]
    # EntityAttributeAssociation: List[CreateEntityAttributeAssociationDTO]
    # -- ^  Need to do entity attribute association after model is imported as we can have attributes with the same name in a model so it difficult to figure out the right attribute to map.


class CreateCloneDTO(BaseModel):
    source_data_model_id: int
    data_model_name: str
    data_model_type: DataModelType
    data_model_version: str
