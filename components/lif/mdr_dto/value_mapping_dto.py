from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CreateValueSetValueMappingDTO(BaseModel):
    # SourceDataModelId: int
    SourceValueSetId: int
    SourceValueId: int
    # TargetDataModelId: int
    TargetValueSetId: int
    TargetValueId: int
    Description: Optional[str] = None
    OriginalValueMappingId: Optional[int] = None
    Notes: Optional[str] = None
    UseConsiderations: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    TransformationGroupId: Optional[int] = None


class ValueSetValueMappingDTO(BaseModel):
    Id: int
    # SourceDataModelId: int
    SourceValueSetId: Optional[int] = None
    SourceValueId: int
    # TargetDataModelId: int
    TargetValueSetId: Optional[int] = None
    TargetValueId: int
    Description: Optional[str] = None
    OriginalValueMappingId: Optional[int] = None
    Notes: Optional[str] = None
    UseConsiderations: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    TransformationGroupId: Optional[int] = None

    class Config:
        orm_mode = True
        from_attributes = True


class UpdateValueSetValueMappingDTO(BaseModel):
    # SourceDataModelId: int
    SourceValueSetId: Optional[int] = None
    SourceValueId: Optional[int] = None
    # TargetDataModelId: int
    TargetValueSetId: Optional[int] = None
    TargetValueId: Optional[int] = None
    Description: Optional[str] = None
    OriginalValueMappingId: Optional[int] = None
    Notes: Optional[str] = None
    UseConsiderations: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    TransformationGroupId: Optional[int] = None
