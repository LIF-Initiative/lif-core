from datetime import datetime
from typing import List, Optional

from lif.mdr_dto.transformation_dto import CreateTransformationDTO, TransformationDTO, UpdateTransformationDTO
from pydantic import BaseModel


class DataModelRefDTO(BaseModel):
    # Data-portable identity of a data model, independent of its primary key.
    name: str
    version: Optional[str] = None
    contributorOrganization: Optional[str] = None


class TransformationGroupDTO(BaseModel):
    Id: Optional[int]
    SourceDataModelId: int
    TargetDataModelId: int
    SourceDataModelName: Optional[str] = None
    TargetDataModelName: Optional[str] = None
    # Populated only when exportable=True: portable (name, version, org) refs.
    SourceDataModel: Optional[DataModelRefDTO] = None
    TargetDataModel: Optional[DataModelRefDTO] = None
    Name: Optional[str] = None
    GroupVersion: Optional[str] = None
    Description: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None  # New column
    ActivationDate: Optional[datetime] = None  # New column
    DeprecationDate: Optional[datetime] = None  # New column
    Contributor: Optional[str] = None  # New column
    ContributorOrganization: Optional[str] = None  # New column
    Transformations: Optional[List[TransformationDTO]] = None
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
    CreationDate: Optional[datetime] = None  # New column
    ActivationDate: Optional[datetime] = None  # New column
    DeprecationDate: Optional[datetime] = None  # New column
    Contributor: Optional[str] = None  # New column
    ContributorOrganization: Optional[str] = None  # New column
    Transformations: Optional[List[CreateTransformationDTO]] = None
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
