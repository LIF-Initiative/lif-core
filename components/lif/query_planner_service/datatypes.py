from pydantic import BaseModel, Field
from typing import List

from lif.datatypes.core import LIFQueryPlanPartTranslation


class LIFQueryPlannerInfoSourceConfig(BaseModel):
    """
    Pydantic model for a LIF Query Planner information source configuration.

    Attributes:
        information_source_id (str): Identifier for the information source.
        information_source_organization (str): Organization owning the information source.
        adapter_id (str): Identifier for the adapter.
        ttl_hours (int): Time-to-live in hours for cached data from this source.
        lif_fragment_paths (List[str]): List of LIF fragment paths provided by this source.
        translations (List[LIFQueryPlanPartTranslation]): List of translations for the information source.
    """

    information_source_id: str = Field(..., description="Identifier for the information source")
    information_source_organization: str = Field(..., description="Organization owning the information source")
    adapter_id: str = Field(..., description="Identifier for the adapter")
    ttl_hours: int = Field(..., description="Time-to-live in hours for cached data from this source")
    lif_fragment_paths: List[str] = Field(..., description="List of LIF fragment paths provided by this source")
    translation: LIFQueryPlanPartTranslation | None = Field(None, description="Translation for the information source")


class LIFQueryPlannerConfig(BaseModel):
    """
    Pydantic model for LIF Query Planner configuration.

    Attributes:
        lif_cache_url (str): URL of the LIF Cache service.
        lif_orchestrator_url (str): URL of the LIF Orchestrator service.
        information_sources_config (List[LIFQueryPlannerInfoSourceConfig]): Configuration for the information sources.
        query_timeout_seconds (int): Maximum time in seconds to wait for a query to complete, including
            orchestration. Used to bound the synchronous polling loop and the internal HTTP clients.
    """

    lif_cache_url: str = Field(..., description="URL of the LIF Cache service")
    lif_orchestrator_url: str = Field(..., description="URL of the LIF Orchestrator service")
    information_sources_config: List[LIFQueryPlannerInfoSourceConfig] = Field(
        ..., description="Configuration for the information sources"
    )
    query_timeout_seconds: int = Field(
        300, gt=0, description="Maximum time in seconds to wait for a query to complete, including orchestration."
    )
