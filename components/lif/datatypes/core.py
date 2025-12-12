import warnings
from typing import Any, Dict, List

from pydantic import BaseModel, Field, RootModel, field_validator


# -------------------------------------------------------------------------
# Pydantic Model
# -------------------------------------------------------------------------
class LIFPerson(RootModel[List[Dict[str, Any]]]):
    """
    Pydantic model for a LIF Person.

    Attributes:
        List[Dict[str, Any]]: List of person attributes.
    """

    root: List[Dict[str, Any]]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]


class LIFPersonIdentifier(BaseModel):
    """
    Pydantic model for a LIF Person Identifier.

    Attributes:
        identifier (str): Identifier value.
        identifierType (str): Identifier type.
    """

    identifier: str = Field(..., description="Identifier value")
    identifierType: str = Field(..., description="Identifier type")


class LIFPersonIdentifiers(BaseModel):
    """
    Pydantic model for a LIF Query Person Identifier list.
    Attributes:
        identifier (List[LIFPersonIdentifier]): Identifier list value.
    """

    identifier: List[LIFPersonIdentifier] = Field(..., description="List of person identifiers")


class LIFRecord(BaseModel):
    """
    Pydantic model for a LIF Record.

    Attributes:
        person (LIFPerson): Person.
    """

    person: LIFPerson = Field(..., description="Person")


class LIFQueryPersonFilter(BaseModel):
    """
    Pydantic model for a LIF Query Person Query.
    Attributes:
        person (LIFPersonFilterIdentifier): Person identifier for the query.
    """

    person: LIFPersonIdentifiers = Field(..., description="Person identifier for the query")


class LIFQueryFilter(RootModel[LIFQueryPersonFilter]):
    """
    Pydantic model for a LIF Query Filter.

    Attributes:
        root (LIFQueryPersonFilter): Root query filter.
    """

    root: LIFQueryPersonFilter


class LIFQuery(BaseModel):
    """
    Pydantic model for a LIF query (GraphQL-like).

    Attributes:
        filter (LIFQueryFilter): Query filter.
        selected_fields (List[str]): Fields to select in projection.
    """

    filter: LIFQueryFilter = Field(..., description="Query filter")
    selected_fields: List[str] = Field(..., description="Fields to select in projection")

    @field_validator("filter")
    @classmethod
    def filter_cannot_be_empty(cls, value):
        if not value:
            raise ValueError("No filter provided.")
        return value


class LIFQueryStatusResponse(BaseModel):
    """
    Pydantic model for a LIF Query Results Status Response.

    Attributes:
        query_id (str): Query ID for the query.
        status (str): Status of the query (e.g., 'PENDING').
        error_message (str | None): Error message if the query failed.
    """

    query_id: str = Field(..., description="Query ID for the query")
    status: str = Field(..., description="Status of the query (e.g., 'PENDING', 'COMPLETED)")
    error_message: str | None = Field(None, description="Error message if the query failed")


class LIFUpdatePersonPayload(BaseModel):
    """
    Pydantic model for a LIF update person payload.

    Attributes:
        filter (Dict[str, Any]): Query filter.
        input (Dict[str, Any]): Fields/values to update.
    """

    filter: Dict[str, Any] = Field(..., description="Mongo-style filter for update")
    input: Dict[str, Any] = Field(..., description="Fields/values to update")

    @field_validator("filter")
    @classmethod
    def filter_cannot_be_empty(cls, value):
        if not value:
            raise ValueError("No filter provided.")
        return value

    @field_validator("input")
    @classmethod
    def input_cannot_be_empty(cls, value):
        if not value:
            raise ValueError("No update fields provided.")
        return value


class LIFUpdate(BaseModel):
    """
    Pydantic model for a LIF update (GraphQL-like).

    Attributes:
        updatePerson (LIFUpdatePersonPayload): Update person.
    """

    updatePerson: LIFUpdatePersonPayload = Field(..., description="Update payload for person")


class LIFFragment(BaseModel):
    """
    Pydantic model for a LIF Fragment.

    Attributes:
        fragment_path (str): Fragment path.
        fragment (List[Dict[str, Any]]): Fragment contents.
    """

    fragment_path: str = Field(..., description="LIF Fragment path")
    fragment: List[Dict[str, Any]] = Field(..., description="Fragment contents")

    @field_validator("fragment_path")
    @classmethod
    def fragment_path_validation(cls, value):
        if not value:
            raise ValueError("No fragment_path provided.")
        if not value.startswith("person."):
            raise ValueError("Fragment path must start with 'person.'")
        return value

    @field_validator("fragment")
    @classmethod
    def fragment_validation(cls, value):
        if len(value) == 0:
            warnings.warn("No fragment entries provided")
        return value


class LIFQueryPlanPartTranslation(BaseModel):
    """
    Pydantic model for a LIF Query Plan Part Translation Section.
    Attributes:
        source_schema_id (str): Identifier for the source schema.
        target_schema_id (str): Identifier for the target schema.
    """

    source_schema_id: str = Field(..., description="Identifier for the source schema")
    target_schema_id: str = Field(..., description="Identifier for the target schema")


class LIFQueryPlanPart(BaseModel):
    """
    Pydantic model for a LIF Query Plan Part.
    Attributes:
        information_source_id (str): Identifier for the information source.
        adapter_identifier (str): Identifier for the adapter.
        person_identifier (LIFPersonIdentifier): Person ID for the orchestration.
        lif_fragment_paths (List[str]): List of LIF Fragment paths to be orchestrated.
        translator (LIFQueryPlanPartTranslatorSection | None): Optional translator section.
    """

    information_source_id: str = Field(..., description="Identifier for the information source")
    adapter_id: str = Field(..., description="Identifier for the adapter")
    person_id: LIFPersonIdentifier = Field(..., description="Person ID for the orchestration")
    lif_fragment_paths: List[str] = Field(..., description="List of LIF Fragment paths to be orchestrated")
    translation: LIFQueryPlanPartTranslation | None = Field(None, description="Optional translation section")


class LIFQueryPlan(RootModel[List[LIFQueryPlanPart]]):
    """
    Pydantic model for a LIF Query Plan.

    Attributes:
        List[LIFQueryPlanPart]: List of LIF query plan parts.
    """

    root: List[LIFQueryPlanPart]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root)
