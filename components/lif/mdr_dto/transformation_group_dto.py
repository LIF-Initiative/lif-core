from datetime import datetime
from typing import List, Optional

from lif.datatypes.mdr_sql_model import AttributeType, ExpressionLanguageType
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


class ImportTransformationAttributeDTO(BaseModel):
    """A source/target attribute inside an imported transformation.

    Only the portable ``EntityIdPath`` (comma-joined ``{DataModelId}:{~}{UniqueName}`` segments) is
    used — resolution is by ``UniqueName``, and every database ID in the file is ignored. No DB IDs
    are required, so a file can be hand-authored without inventing them. An exported file's extra
    fields (``AttributeId``, ``EntityId``, ``AttributeType``, ...) are accepted and ignored.
    """

    EntityIdPath: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None


class ImportTransformationDTO(BaseModel):
    """A transformation inside an import file. DB IDs (``Id``, ``TransformationGroupId``) are not
    required — they are ignored on import — so the file need not carry them."""

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
    SourceAttributes: Optional[List[ImportTransformationAttributeDTO]] = None
    TargetAttribute: Optional[ImportTransformationAttributeDTO] = None


class ImportTransformationGroupRequestDTO(BaseModel):
    """Request body for POST /transformation_groups/{transformation_group_id}/import.

    Mirrors the shape emitted by the export endpoint so an exported file round-trips as-is, but with
    every database ID optional so a file can also be edited or authored by hand.

    Data portability: every database ID present in the file is IGNORED for matching — the group
    ``Id``, ``SourceDataModelId``/``TargetDataModelId``, and the numeric ``{DataModelId}:`` prefixes
    inside each ``EntityIdPath`` are all authored by whatever instance produced the file. The only
    ID matched against this database is the ``transformation_group_id`` in the route path; source
    and target data models are derived from it. Entity/attribute paths are resolved portably by
    ``UniqueName``. The group version comes from the ``version`` query parameter, not the file.
    """

    Name: Optional[str] = None
    Description: Optional[str] = None
    Notes: Optional[str] = None
    CreationDate: Optional[datetime] = None
    ActivationDate: Optional[datetime] = None
    DeprecationDate: Optional[datetime] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Tags: Optional[str] = None
    Transformations: Optional[List[ImportTransformationDTO]] = None


class TransformationImportNonMatchDTO(BaseModel):
    """A source/target attribute path from the import file that could not be applied.

    A non-match is either an entity/attribute ``UniqueName`` that does not resolve in the target
    database, or a path that resolves by name but does not form a valid chain in the anchor data
    model. Governed by ``allowMissingPaths``.
    """

    TransformationName: Optional[str] = None
    AttributeType: AttributeType  # Source or Target
    NamedPath: Optional[str] = None
    Reason: str


class ImportTransformationGroupResultDTO(BaseModel):
    Success: bool
    TransformationGroupId: Optional[int] = None
    ImportedTransformationCount: int = 0
    SkippedTransformationCount: int = 0
    MissingPaths: List[TransformationImportNonMatchDTO] = []
