from typing import Any, Dict

from fastapi import APIRouter, Query, Request
from lif.datatypes.core import TargetTransformationDataModelDTO, TargetTransformationDataModelsDTO
from lif.lif_schema_config.core import LIFSchemaConfig
from lif.mdr_client.core import fetch_data_models_from_mdr
from lif.mdr_utils.logger_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Load centralized configuration from environment
# get_settings() could be used, but the mdr_client is already setup with this flow
CONFIG = LIFSchemaConfig.from_environment()

logger.info(f"LIF_QUERY_PLANNER_URL: {CONFIG.query_planner_base_url}")
logger.info(f"LIF_GRAPHQL_ROOT_TYPE_NAME: {CONFIG.root_type_name}")
logger.info(f"LIF_MDR_API_URL: {CONFIG.mdr_api_url}")


@router.get("/exports", response_model=Dict[str, Any])
async def get_data(
    request: Request,
    learner_id: str = Query(..., alias="learnerId"),
    data_model_name: str = Query(..., alias="dataModelName"),
    data_model_version: str = Query(..., alias="dataModelVersion"),
    data_model_contributor_organization: str = Query(..., alias="dataModelContributorOrganization"),
    transformation_id: str = Query(..., alias="transformationId"),
):
    """Endpoint to export learner data in a specified format.

    The response model is intentionally generic since it will depend
    on the requested data format and transformation.
    """

    logger.info(
        (
            "Received request for learner data export as %s - learnerId: %s, "
            "dataModelName: %s, dataModelVersion: %s, "
            "dataModelContributorOrganization: %s, transformationId: %s"
        ),
        request.state.principal,
        learner_id,
        data_model_name,
        data_model_version,
        data_model_contributor_organization,
        transformation_id,
    )

    # Confirm transform target is valid for user

    # Retrieve Org LIF schema from MDR

    data_models = fetch_data_models_from_mdr(
        CONFIG, data_model_name, data_model_version, data_model_contributor_organization
    )

    logger.info(f"Data models fetched from MDR: {data_models.total}")

    # Retrieve learner data from Query Planner

    # async with httpx.AsyncClient() as client:
    #     response = await client.post(CONFIG.query_planner_query_url, json=openapi)
    #     if response.status_code == 200:
    #         response_json = response.json()
    #         logger.info("Successfully retrieved learner data from Query Planner: %s", str(response_json))

    # Transform data with Translator

    return {"total": "data"}


@router.get("/available-data-formats", response_model=TargetTransformationDataModelsDTO)
async def get_available_data_formats(request: Request):
    # TODO: Build this out.
    logger.info("Received request for available data formats as %s", request.state.principal)

    data_formats = TargetTransformationDataModelsDTO(
        metadata={"total": 3},
        DataFormats=[
            TargetTransformationDataModelDTO(
                name="OpenBadges 3.0",
                version="1.0.3",
                contributorOrganization="OB",
                TransformationVersions=["1.0.0", "1.1.0"],
            ),
            TargetTransformationDataModelDTO(
                name="CEDS", version="2.0.0", contributorOrganization="CEDS Org", TransformationVersions=["2.0.0"]
            ),
            TargetTransformationDataModelDTO(
                name="ExampleDataSource",
                version="1.0.1",
                contributorOrganization="Community",
                TransformationVersions=["1.3.0"],
            ),
        ],
    )
    return data_formats
