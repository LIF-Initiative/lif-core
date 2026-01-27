from datetime import datetime
from typing import List, Optional

from lif.datatypes.mdr_sql_model import ExpressionLanguageType
from pydantic import BaseModel


class TransformationAttributeDTO(BaseModel):
    AttributeId: int
    EntityId: Optional[int] = None  # Existing column
    AttributeName: Optional[str] = None
    AttributeType: str  # Either 'Source' or 'Target'
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    EntityIdPath: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class CreateTransformationAttributeDTO(BaseModel):
    AttributeId: Optional[int] = None  # No longer used
    EntityId: Optional[int] = None  # Existing column
    # AttributeName: Optional[str] = None
    # EntityName: Optional[str] = None
    AttributeType: str  # Either 'Source' or 'Target'
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    EntityIdPath: Optional[str] = None


class UpdateTransformationAttributeDTO(BaseModel):
    AttributeId: Optional[int] = None
    EntityId: Optional[int] = None  # Existing column
    # AttributeName: Optional[str] = None
    # EntityName: Optional[str] = None
    AttributeType: Optional[str] = None  # Either 'Source' or 'Target'
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    EntityIdPath: Optional[str] = None


class TransformationDTO(BaseModel):
    Id: Optional[int]
    # SourceDataModelId: int
    # TargetDataModelId: int
    TransformationGroupId: Optional[int]
    # SourceDataModelName: Optional[str] = None
    # TargetDataModelName: Optional[str] = None
    Name: Optional[str] = None
    Expression: Optional[str] = None
    ExpressionLanguage: Optional[ExpressionLanguageType] = None
    Notes: Optional[str] = None
    Alignment: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    # There is one transformation for which we do not have transformation attribute -Program.Program Participation.Exit Reason  - between CEDS and LIF 1.0
    SourceAttributes: Optional[List[TransformationAttributeDTO]] = None  # Source attributes
    TargetAttribute: Optional[TransformationAttributeDTO] = None  # Target attribute

    class Config:
        orm_mode = True
        from_attributes = True


class CreateTransformationDTO(BaseModel):
    # SourceDataModelId: int
    # TargetDataModelId: int
    TransformationGroupId: int
    Name: Optional[str] = None
    Expression: str
    ExpressionLanguage: Optional[ExpressionLanguageType] = ExpressionLanguageType.JSONata
    Notes: Optional[str] = None
    Alignment: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    SourceAttributes: List[CreateTransformationAttributeDTO]  # Source attributes
    TargetAttribute: CreateTransformationAttributeDTO  # Target attribute

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class UpdateTransformationDTO(BaseModel):
    # SourceDataModelId: Optional[int] = None
    # TargetDataModelId: Optional[int] = None
    Id: Optional[int] = None
    TransformationGroupId: Optional[int] = None
    Name: Optional[str] = None
    Expression: Optional[str] = None
    ExpressionLanguage: Optional[ExpressionLanguageType] = None
    Notes: Optional[str] = None
    Alignment: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    SourceAttributes: Optional[List[UpdateTransformationAttributeDTO]] = None  # Source attribute
    TargetAttribute: Optional[UpdateTransformationAttributeDTO] = None  # Target attribute

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class CreateTransformationWithTransformationGroupDTO(BaseModel):
    # SourceDataModelId: int
    # TargetDataModelId: int
    # TransformationGroupId: Optional[int] = None
    Name: Optional[str] = None
    Expression: str
    ExpressionLanguage: Optional[ExpressionLanguageType] = None
    Notes: Optional[str] = None
    Alignment: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    SourceAttributes: List[CreateTransformationAttributeDTO]  # Source attributes
    TargetAttribute: CreateTransformationAttributeDTO  # Target attribute

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class TransformationGroupWithTransformationsDTO(BaseModel):
    Id: Optional[int]
    SourceDataModelId: int
    TargetDataModelId: int
    Name: Optional[str] = None
    GroupVersion: str = None
    Description: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Transformations: Optional[List[TransformationDTO]] = None
    Tags: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True


class TransformationGroupDTO(BaseModel):
    Id: Optional[int]
    SourceDataModelId: int
    TargetDataModelId: int
    # Friendly names for source/target models (populated in service layer)
    SourceDataModelName: Optional[str] = None
    TargetDataModelName: Optional[str] = None
    Name: Optional[str] = None
    GroupVersion: str = None
    Description: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Tags: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True


class CreateTransformationGroupDTO(BaseModel):
    SourceDataModelId: int
    TargetDataModelId: int
    Name: Optional[str] = None
    GroupVersion: str
    Description: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Tags: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class UpdateTransformationGroupDTO(BaseModel):
    SourceDataModelId: Optional[int] = None
    TargetDataModelId: Optional[int] = None
    Name: Optional[str] = None
    GroupVersion: Optional[str] = None
    Description: Optional[str] = None
    Notes: Optional[str] = None
    Alignment: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Transformations: Optional[List[UpdateTransformationDTO]] = None
    Tags: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class TransformationListDTO(BaseModel):
    SourceTransformations: List[TransformationDTO]
    TargetTransformations: List[TransformationDTO]

    class Config:
        orm_mode = True
        from_attributes = True


class GetALLTransformationsDTO(BaseModel):
    TransformationGroupId: int
    SourceDataModelId: int
    TargetDataModelId: int
    TransformationGroupName: Optional[str] = None
    TransformationGroupVersion: str = None
    TransformationGroupDescription: Optional[str] = None
    TransformationGroupNotes: Optional[str] = None
    TransformationId: Optional[int] = None
    TransformationExpression: Optional[str] = None
    TransformationExpressionLanguage: Optional[ExpressionLanguageType] = None
    TransformationNotes: Optional[str] = None
    TransformationAlignment: Optional[str] = None
    TransformationCreationDate: Optional[datetime] = None
    TransformationActivationDate: Optional[datetime] = None
    TransformationDeprecationDate: Optional[datetime] = None
    TransformationContributor: Optional[str] = None
    TransformationContributorOrganization: Optional[str] = None
    TransformationSourceAttributes: Optional[List[TransformationAttributeDTO]] = None
    TransformationTargetAttribute: Optional[TransformationAttributeDTO] = None

    class Config:
        orm_mode = True
        from_attributes = True
