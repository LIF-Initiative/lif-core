from lif.mdr_dto.datamodel_dto import DataModelDTO
from pydantic import BaseModel, Field


class MdrRetrieveDataModelsDTO(BaseModel):
    """
    Model for the response from MDR when retrieving data models.

    Attributes:
        total: Total number of data models matching the query
        dataModels: List of data models matching the query
    """

    total: int = Field(..., description="Total number of data models matching the query")
    data: list[DataModelDTO] = Field(..., description="List of data models matching the query")
