from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EntityAttributeAssociationDTO(BaseModel):
    Id: int
    EntityId: int
    AttributeId: int
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    ExtendedByDataModelId: Optional[int] = None
    Name: Optional[str] = None
    Array: Optional[bool] = None
    # Extension: bool
    # ExtensionNotes: Optional[str]

    class Config:
        orm_mode = True
        from_attributes = True  # This enables the use of `from_orm`


class CreateEntityAttributeAssociationDTO(BaseModel):
    EntityId: int
    AttributeId: int
    # ParentEntityName: Optional[str] = None
    # ChildEntityName: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: Optional[bool] = False
    ExtensionNotes: Optional[str] = None
    ExtendedByDataModelId: Optional[int] = None
    # Not sent, or null: the rule's value (association_name.py, #1472).
    Name: Optional[str] = None
    Array: Optional[bool] = None


class UpdateEntityAttributeAssociationDTO(BaseModel):
    EntityId: Optional[int] = None
    AttributeId: Optional[int] = None
    # ParentEntityName: Optional[str] = None
    # ChildEntityName: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Extension: Optional[bool] = False
    ExtensionNotes: Optional[str] = None
    ExtendedByDataModelId: Optional[int] = None
    # Not sent: kept, or still the rule's if it was. Null: back to the rule's value (#1472).
    Name: Optional[str] = None
    Array: Optional[bool] = None
