from http import HTTPStatus
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request
from lif.datatypes.core import TargetTransformationDataModelDTO, TargetTransformationDataModelsDTO
from lif.datatypes.mdr_consumer import MdrRetrieveDataModelsDTO
from lif.lif_schema_config.core import LIFSchemaConfig
from lif.mdr_client.core import MDRClientException, fetch_data_models_from_mdr
from lif.mdr_utils.logger_config import get_logger
from lif.query_planner_client import QueryPlannerException, fetch_query_from_query_planner
from lif.translator_client import TranslatorException, translate_learner_data

router = APIRouter()
logger = get_logger(__name__)

# Load centralized configuration from environment
# get_settings() could be used, but the mdr_client is already setup with this flow
CONFIG = LIFSchemaConfig.from_environment()

logger.info(f"LIF_QUERY_PLANNER_URL: {CONFIG.query_planner_base_url}")
logger.info(f"LIF_TRANSLATOR_BASE_URL: {CONFIG.translator_base_url}")
logger.info(f"LIF_MDR_API_URL: {CONFIG.mdr_api_url}")


@router.get("/exports", response_model=Dict[str, Any])
async def get_data(
    request: Request,
    learner_id: str = Query(..., alias="learnerId"),
    data_model_name: str = Query(..., alias="dataModelName"),
    data_model_version: str = Query(..., alias="dataModelVersion"),
    data_model_contributor_organization: str = Query(..., alias="dataModelContributorOrganization"),
):
    """Endpoint to export learner data in a specified format.

    The response model is intentionally generic since it will depend
    on the requested data format and transformation.
    """

    logger.info(
        (
            "Received request for learner data export as %s - learnerId: %s, "
            "dataModelName: %s, dataModelVersion: %s, "
            "dataModelContributorOrganization: %s"
        ),
        request.state.principal,
        learner_id,
        data_model_name,
        data_model_version,
        data_model_contributor_organization,
    )

    source_schema_id = CONFIG.openapi_data_model_id
    if source_schema_id is None:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="OPENAPI_DATA_MODEL_ID is not configured"
        )

    try:
        data_models_raw = fetch_data_models_from_mdr(
            CONFIG, data_model_name, data_model_version, data_model_contributor_organization
        )
    except MDRClientException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Unable to retrieve data models from MDR"
        ) from e
    data_models = MdrRetrieveDataModelsDTO(**data_models_raw)
    data_models_count = len(data_models.data)

    if data_models_count > 1:
        error_msg = "Found multiple target data models from query parameters"
        logger.error("%s - %s", error_msg, data_models_count)
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=error_msg)

    if data_models_count == 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Unable to determine target data model from query parameters"
        )

    target_schema_id = data_models.data[0].Id
    if target_schema_id is None:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Data model returned from MDR has no Id"
        )

    logger.info(f"Data model fetched from MDR: {target_schema_id}")

    # Retrieve learner data from Query Planner

    # FUTURE WORK: identifierType and selected_fields are hardcoded; both should be
    # derived from the caller's context or the target data model's requirements.
    lif_query = {
        "filter": {"Person": {"Identifier": [{"identifier": learner_id, "identifierType": "SCHOOL_ASSIGNED_NUMBER"}]}},
        "selected_fields": [
            "Person.Name",
            "Person.Contact",
            "Person.Identifier",
            "Person.EmploymentLearningExperience",
            "Person.PositionPreferences",
            "Person.CredentialAward",
            "Person.CourseLearningExperience",
            "Person.Proficiency",
            "Person.EmploymentPreferences",
        ],
    }
    try:
        lif_learner_data = await fetch_query_from_query_planner(CONFIG.query_planner_base_url, lif_query)
    except QueryPlannerException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Unable to retrieve learner data from Query Planner"
        ) from e

    logger.debug(f"LIF learner data returned from Query Planner: {lif_learner_data}")

    if not lif_learner_data:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Query Planner did not find any results for learnerId: {learner_id}",
        )

    if len(lif_learner_data) > 1:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Query Planner returned multiple results for learnerId: {learner_id}",
        )

    # Transform data with Translator

    try:
        translated_data = await translate_learner_data(
            CONFIG.translator_base_url,
            source_schema_id=source_schema_id,
            target_schema_id=str(target_schema_id),
            learner_data=lif_learner_data[0],
        )
    except TranslatorException as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Unable to translate the learner data from the LIF model into the target model",
        ) from e

    logger.info(
        "Successfully translated learner data from data model %s into data model %s", source_schema_id, target_schema_id
    )
    return translated_data


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
