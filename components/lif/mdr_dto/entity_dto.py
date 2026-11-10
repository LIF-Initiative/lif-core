from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EntityDTO(BaseModel):
    Id: Optional[int]
    Name: str
    UniqueName: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    DataModelId: int
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None
    Tags: Optional[str] = None
    Common: Optional[bool] = None

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class ChildEntityDTO(BaseModel):
    Id: Optional[int]
    Name: str
    UniqueName: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    DataModelId: int
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None
    Tags: Optional[str] = None
    Common: Optional[bool] = None
    ParentEntityId: Optional[int] = None  # Added for child entities
    Relationship: Optional[str] = None
    Placement: Optional[str] = None
    AssociationArray: Optional[bool] = None  # Whether the child is a list under this parent (#1429)

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class CreateEntityDTO(BaseModel):
    Name: str
    UniqueName: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    DataModelId: int
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: bool = False
    ExtensionNotes: Optional[str] = None
    Tags: Optional[str] = None
    Common: Optional[bool] = None


class UpdateEntityDTO(BaseModel):
    Name: Optional[str] = None
    UniqueName: Optional[str] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Required: Optional[str] = None
    Array: Optional[str] = None
    SourceModel: Optional[str] = None
    DataModelId: Optional[int] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: Optional[bool] = False
    ExtensionNotes: Optional[str] = None
    Tags: Optional[str] = None
    Common: Optional[bool] = None


# class EntityAttributeDTO(BaseModel):
#     Entity: EntityDTO
#     Attributes: List[AttributeDTO]
