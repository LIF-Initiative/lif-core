"""Pydantic models for the three MDR portable file kinds: model, mapping group and crosswalk.

The format is specified in docs/specs/mdr-portable-file-format.md. Fields are declared in the order
the spec lists them, which is the canonical key order (§9). These models check each object's shape
only; rules that span elements (keys, references, cycles, paths) belong to the converter.

ActivationDate and DeprecationDate are descriptive content, carried as stored: nothing reads them
as a condition. The one exception is MappingGroupDetails, whose activation is local to each install
and so is not carried (§6.1). A date that starts controlling behavior moves out of the format.
DataModelDetails keeps both dates as content for now, although the MDR frontend fills its
ActivationDate with the creation time, which makes it closer to an install-local fact.

CreationDate is not carried: import sets it to the import time, so the round trip stays exact.
"""

from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional, Union

from lif.mdr_dto.transformation_group_dto import reject_non_numeric_group_version
from lif.mdr_sql_model.core import AccessType
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictBool,
)

# Parsing is strict: a key the format version does not define is refused (§4.2).
_STRICT = ConfigDict(extra="forbid")


def _require_int(value: object) -> object:
    # Python treats `True` and `1.0` as equal to 1; neither is a format version.
    if type(value) is not int:
        raise ValueError("Format.Version must be an integer")
    return value


FormatVersion = Annotated[Literal[1], BeforeValidator(_require_int)]

# Identity fields are required and non-empty (§2).
IdentityStr = Annotated[str, Field(min_length=1)]


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty or only whitespace")
    return value


def _format_timestamp(value: datetime) -> str:
    # §9: RFC 3339 in UTC with Z; fractional seconds only when non-zero, trailing zeros dropped.
    utc = value.astimezone(timezone.utc)
    text = utc.strftime("%Y-%m-%dT%H:%M:%S")
    if utc.microsecond:
        text += f".{utc.microsecond:06d}".rstrip("0")
    return text + "Z"


Timestamp = Annotated[AwareDatetime, PlainSerializer(_format_timestamp, when_used="json")]


# --- Envelope (§4.1) ---


class ModelFormat(BaseModel):
    model_config = _STRICT

    Type: Literal["lif-mdr-model"]
    Version: FormatVersion


class MappingGroupFormat(BaseModel):
    model_config = _STRICT

    Type: Literal["lif-mdr-mapping-group"]
    Version: FormatVersion


class CrosswalkFormat(BaseModel):
    model_config = _STRICT

    Type: Literal["lif-mdr-crosswalk"]
    Version: FormatVersion


# --- Identities and element references (§2, §4.3) ---


class ModelIdentity(BaseModel):
    model_config = _STRICT

    Name: IdentityStr
    Version: IdentityStr
    ContributorOrganization: IdentityStr


class EntityKey(BaseModel):
    model_config = _STRICT

    Entity: str


class AttributeKey(BaseModel):
    model_config = _STRICT

    Attribute: str


class ValueSetKey(BaseModel):
    model_config = _STRICT

    ValueSet: str


# --- Model file (§5) ---


class DataModelDetails(BaseModel):
    model_config = _STRICT

    Name: IdentityStr
    Version: IdentityStr
    ContributorOrganization: IdentityStr
    CopiedFrom: Optional[ModelIdentity] = None
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    State: Optional[str] = None
    Tags: Optional[str] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class Value(BaseModel):
    model_config = _STRICT

    ValueName: str
    Value: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Source: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class ValueSet(BaseModel):
    model_config = _STRICT

    Name: str
    Values: List[Value]
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Tags: Optional[str] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class Entity(BaseModel):
    model_config = _STRICT

    UniqueName: str
    Name: str
    LevelOfAccess: AccessType
    Queryable: StrictBool
    Modifiable: StrictBool
    Required: StrictBool = False
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    SourceModel: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Tags: Optional[str] = None
    Common: Optional[StrictBool] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class Attribute(BaseModel):
    model_config = _STRICT

    UniqueName: str
    Name: str
    DataType: str
    ValueSet: Optional[ValueSetKey] = None
    LevelOfAccess: AccessType
    Queryable: StrictBool
    Modifiable: StrictBool
    Required: StrictBool = False
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    SourceModel: Optional[str] = None
    Example: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Tags: Optional[str] = None
    Common: Optional[StrictBool] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class Association(BaseModel):
    model_config = _STRICT

    Parent: EntityKey
    Child: Union[EntityKey, AttributeKey]
    Name: str
    Array: StrictBool = False
    Reference: StrictBool = False
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class ModelFile(BaseModel):
    model_config = _STRICT

    Format: ModelFormat
    Details: DataModelDetails
    ValueSets: List[ValueSet]
    Entities: List[Entity]
    Attributes: List[Attribute]
    Associations: List[Association]


# --- Mapping-group file (§6) ---


class MappingGroupDetails(BaseModel):
    # No ActivationDate or DeprecationDate: activation is local to each install (§6.1).
    model_config = _STRICT

    Source: ModelIdentity
    Target: ModelIdentity
    Version: Annotated[str, AfterValidator(reject_non_numeric_group_version)]
    Name: Annotated[str, AfterValidator(_reject_blank)]
    Description: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    Tags: Optional[str] = None


class MappingPath(BaseModel):
    model_config = _STRICT

    Path: str
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class Mapping(BaseModel):
    model_config = _STRICT

    Target: MappingPath
    Sources: List[MappingPath]
    ExpressionLanguage: Literal["JSONata"]
    Expression: str
    Name: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Alignment: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class MappingGroupFile(BaseModel):
    model_config = _STRICT

    Format: MappingGroupFormat
    Details: MappingGroupDetails
    Mappings: List[Mapping]


# --- Crosswalk file (§7) ---


class CrosswalkValueSetKey(BaseModel):
    # The one reference that names its model, by identity (§4.3).
    model_config = _STRICT

    Model: ModelIdentity
    ValueSet: str


class CrosswalkDetails(BaseModel):
    # The crosswalk's key. No row stores anything else about a crosswalk as a whole.
    model_config = _STRICT

    Source: CrosswalkValueSetKey
    Target: CrosswalkValueSetKey


class CrosswalkEntry(BaseModel):
    model_config = _STRICT

    Source: str
    Target: str
    Description: Optional[str] = None
    UseConsiderations: Optional[str] = None
    Notes: Optional[str] = None
    Contributor: Optional[str] = None
    ContributorOrganization: Optional[str] = None
    ActivationDate: Optional[Timestamp] = None
    DeprecationDate: Optional[Timestamp] = None


class CrosswalkFile(BaseModel):
    model_config = _STRICT

    Format: CrosswalkFormat
    Details: CrosswalkDetails
    Entries: List[CrosswalkEntry]
